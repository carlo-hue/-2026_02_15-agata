# agata/admin/routes/catalogs/ztf.py
"""
Endpoint per catalogo ZTF (Zwicky Transient Facility).

ZTF fornisce dati fotometrici ground-based in bande g, r, i.
Survey del Nord (Dec > -30 deg), profondita' ~20-21 mag.

API Light Curves: https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves
"""

import io
import logging
from typing import Optional, Tuple

import pandas as pd
import requests
from flask import request, jsonify
from flask_login import login_required, current_user

from . import catalogs_bp
from .common import (
    get_db_session,
    validate_coordinates,
    resolve_gaia_id,
    resolve_gaia_coordinates,
    create_import_record,
    update_import_with_results,
    insert_catalog_data,
    finalize_import,
    get_import_record,
    normalize_time,
    can_create_new_star,
    can_add_data_to_star,
)
from agata.admin.decorators import admin_required
from agata.auth_models import Project

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAZIONE ZTF/IRSA
# =============================================================================

IRSA_LIGHTCURVES_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
TIMEOUT_SECONDS = 180  # IRSA può essere lento
ZTF_DEFAULT_RADIUS_DEG = 0.00278  # ~10 arcsec, come da riferimento utente

# Mapping filtercode IRSA → nome catalogo in Cataloghi_esterni
ZTF_FILTER_MAP = {
    'zr': 'ZTFr',
    'zg': 'ZTFg',
    'zi': 'ZTFi',
}


# =============================================================================
# FUNZIONI SPECIFICHE ZTF
# =============================================================================

def _query_ztf_lightcurve(ra: float, dec: float, radius_deg: float) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Interroga IRSA per lightcurve ZTF via POS=CIRCLE ra dec radius.

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        radius_deg: Raggio ricerca in gradi

    Returns:
        Tuple (DataFrame con dati, error_message)
        DataFrame ha colonne: hjd, mag, mag_err, filtercode
    """
    # Controllo copertura ZTF
    if dec < -30:
        return None, "Coordinate fuori dalla copertura ZTF (Dec > -30)"

    params = {
        "POS": f"CIRCLE {ra} {dec} {radius_deg}",
        "BANDNAME": "g,r,i",
        "FORMAT": "csv",
        "BAD_CATFLAGS_MASK": "32768",
    }

    try:
        resp = requests.get(IRSA_LIGHTCURVES_URL, params=params, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        content = resp.text.strip()

        # Nessun dato
        if not content or content.startswith('<!DOCTYPE') or 'No data found' in content:
            return None, "Nessun dato ZTF trovato per queste coordinate"

        df = _parse_ztf_csv(content)
        if df is None or df.empty:
            return None, "Nessun dato valido nella risposta ZTF"

        return df, None

    except requests.Timeout:
        return None, "Timeout connessione IRSA/ZTF"
    except requests.RequestException as e:
        return None, f"Errore connessione IRSA: {e}"
    except Exception as e:
        logger.error(f"ZTF query error: {e}", exc_info=True)
        return None, str(e)


def _parse_ztf_csv(response_text: str) -> Optional[pd.DataFrame]:
    """
    Parse CSV response ZTF in DataFrame standard.

    Colonne ZTF input: oid, expid, hjd, mjd, mag, magerr, catflags, filtercode, ...
    Colonne output: hjd, mag, mag_err, filtercode
    """
    try:
        lines = [l for l in response_text.splitlines() if not l.startswith('#')]
        cleaned_text = '\n'.join(lines)

        if not cleaned_text.strip():
            return None

        df = pd.read_csv(io.StringIO(cleaned_text))
        if df.empty:
            return None

        required_cols = ['mjd', 'mag']
        if not all(col in df.columns for col in required_cols):
            logger.warning(f"ZTF CSV mancante colonne necessarie: {df.columns.tolist()}")
            return None

        result = pd.DataFrame({
            'hjd': normalize_time(df['mjd'], 'mjd'),
            'mag': df['mag'],
            'mag_err': df.get('magerr', pd.Series([None]*len(df))),
        })

        if 'filtercode' in df.columns:
            result['filtercode'] = df['filtercode']

        result = result.dropna(subset=['hjd', 'mag']).sort_values('hjd').reset_index(drop=True)
        return result

    except Exception as e:
        logger.error(f"Errore parsing ZTF CSV: {e}")
        return None


def _get_ztf_band_stats(df: pd.DataFrame) -> dict:
    """
    Calcola statistiche per banda dal DataFrame ZTF.
    """
    if 'filtercode' not in df.columns:
        return {'predominant': 'ZTF-r', 'counts': {}}

    counts = df['filtercode'].value_counts().to_dict()
    predominant = f"ZTF-{list(counts.keys())[0]}" if counts else "ZTF-r"
    counts = {f"ZTF-{k}": v for k, v in counts.items()}
    return {'predominant': predominant, 'counts': counts}


# =============================================================================
# ENDPOINT ZTF
# =============================================================================

@catalogs_bp.route('/api/catalogs/ztf/search', methods=['POST'])
@login_required
@admin_required('analyst')  # Analyst può cercare per stelle assegnate
def search_ztf():
    """
    Ricerca dati ZTF per Gaia ID o coordinate.
    """
    data = request.get_json() or {}
    input_gaia_id = data.get('gaia_id')
    radius_arcsec = float(data.get('radius_arcsec', 5.0))

    db = get_db_session()
    try:
        if input_gaia_id:
            # Gaia ID -> coordinate
            gaia_info = resolve_gaia_id_by_source_id(input_gaia_id)
            if not gaia_info:
                return jsonify({'error': f"Gaia ID {input_gaia_id} non trovato"}), 404
            ra, dec = gaia_info['ra'], gaia_info['dec']
            gaia_id = input_gaia_id
        else:
            valid, error, ra, dec = validate_coordinates(data.get('ra'), data.get('dec'))
            if not valid:
                return jsonify({'error': error}), 400
            gaia_id = None

        radius_deg = radius_arcsec / 3600.0
        df, query_error = _query_ztf_lightcurve(ra, dec, radius_deg)

        search_value = gaia_id if gaia_id else f"{ra:.6f},{dec:.6f}"
        search_type = 'gaia_id' if gaia_id else 'coordinates'

        import_record = create_import_record(
            db=db,
            catalog_name='ZTF',
            search_type=search_type,
            search_value=search_value,
            ra=ra,
            dec=dec,
            radius_arcsec=radius_arcsec,
            gaia_id=gaia_id,
            user_id=current_user.id
        )

        if df is None or df.empty:
            update_import_with_results(
                db=db,
                import_record=import_record,
                catalog_name='ZTF',
                success=False,
                point_count=0,
                error_message=query_error or "Nessun dato trovato"
            )
            return jsonify({
                'success': False,
                'catalog': 'ZTF',
                'import_id': import_record.id,
                'error': query_error or "Nessun dato ZTF trovato",
                'gaia_id': gaia_id
            }), 404

        band_stats = _get_ztf_band_stats(df)
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name='ZTF',
            success=True,
            point_count=len(df),
            band=band_stats['predominant'],
            time_range=time_range,
            mag_range=mag_range
        )

        preview_data = df.head(100).to_dict(orient='records')

        return jsonify({
            'success': True,
            'catalog': 'ZTF',
            'import_id': import_record.id,
            'point_count': len(df),
            'gaia_id': gaia_id,
            'band_stats': band_stats,
            'time_range': {'min': time_range[0], 'max': time_range[1], 'span_days': time_range[1]-time_range[0]},
            'mag_range': {'min': mag_range[0], 'max': mag_range[1]},
            'preview': preview_data,
            'message': f"Trovati {len(df)} punti ZTF ({band_stats['predominant']})"
        })

    except Exception as e:
        db.rollback()
        logger.error(f"ZTF search error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'ZTF'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/ztf/import/<int:import_id>', methods=['POST'])
@login_required
@admin_required('analyst')
def import_ztf(import_id: int):
    """
    Importa dati ZTF in database.
    """
    data = request.get_json() or {}
    gaia_id = data.get('gaia_id')
    if not gaia_id:
        return jsonify({'error': 'gaia_id obbligatorio'}), 400

    db = get_db_session()
    try:
        import_record, error = get_import_record(
            db, import_id, current_user.id, current_user.role == 'superuser'
        )
        if error:
            return jsonify({'error': error}), 404 if 'non trovato' in error else 403

        can_add, add_error, existing_project = can_add_data_to_star(
            db, gaia_id, current_user.role, current_user.association_id, current_user.id
        )

        auto_create_project = False
        if not can_add:
            can_create, create_error = can_create_new_star(db, current_user.role, current_user.association_id)
            if not can_create:
                return jsonify({'error': add_error or create_error, 'catalog': 'ZTF'}), 403
            auto_create_project = True

        import_record.resolved_gaia_id = gaia_id
        import_record.state = 'importing'
        db.commit()

        radius_deg = (import_record.search_radius_arcsec or 5.0) / 3600.0
        df, query_error = _query_ztf_lightcurve(import_record.resolved_ra, import_record.resolved_dec, radius_deg)

        if df is None or df.empty:
            import_record.state = 'failed'
            import_record.error_message = query_error or "Nessun dato nella ri-query"
            db.commit()
            return jsonify({'success': False, 'error': query_error or "Nessun dato ZTF", 'catalog': 'ZTF'}), 400

        insert_df = df[['hjd', 'mag', 'mag_err']] if 'mag_err' in df.columns else df[['hjd', 'mag']]
        points_imported = insert_catalog_data(
            db, gaia_id, 'ZTF', insert_df,
            catalog_import_id=import_record.id
        )

        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({'success': False, 'error': "Nessun punto importato", 'catalog': 'ZTF'}), 400

        association_id = current_user.association_id if auto_create_project and current_user.role == 'admin' else None
        success, error, created_project = finalize_import(
            db=db,
            import_record=import_record,
            points_imported=points_imported,
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=association_id,
            auto_create_project=auto_create_project,
            catalog_name='ZTF'
        )

        if not success:
            return jsonify({'error': error, 'catalog': 'ZTF'}), 400

        response = {
            'success': True,
            'catalog': 'ZTF',
            'import_id': import_id,
            'points_imported': points_imported,
            'gaia_id': gaia_id,
            'message': f'Importati {points_imported} punti ZTF'
        }

        if created_project:
            response.update({
                'project_created': True,
                'project_id': created_project.id,
                'project_code': created_project.project_code
            })
            response['message'] += f" - Creato progetto {created_project.project_code}"

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"ZTF import error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'ZTF'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/ztf/search-and-import', methods=['POST'])
@login_required
@admin_required('analyst')
def search_and_import_ztf():
    """
    Ricerca e importa dati ZTF in un unico step (per tab Import Cataloghi editor).

    A differenza di TESS QLP (2 step: search → download), ZTF restituisce
    tutti i dati in una singola chiamata IRSA. Questo endpoint cerca e importa
    direttamente, separando per filtro (ZTFr, ZTFg, ZTFi).

    Request JSON:
        - gaia_id (str): Gaia DR3 source ID

    Response:
        - success (bool)
        - gaia_id (str)
        - total_points (int)
        - bands (dict): {ZTFr: N, ZTFg: N, ZTFi: N}
        - time_range (dict): {min, max, span_days}
        - mag_range (dict): {min, max}
    """
    data = request.get_json() or {}
    gaia_id = data.get('gaia_id')

    if not gaia_id:
        return jsonify({'error': 'gaia_id obbligatorio'}), 400

    db = get_db_session()
    try:
        # Step 1: Risolvi coordinate da Gaia ID
        logger.info(f"[ZTF Import] Resolving Gaia ID {gaia_id}")
        gaia_info = resolve_gaia_coordinates(gaia_id)
        if not gaia_info:
            return jsonify({'error': f'Gaia ID {gaia_id} non trovato in DR3/DR2'}), 404

        ra = gaia_info['ra']
        dec = gaia_info['dec']
        logger.info(f"[ZTF Import] Gaia {gaia_id} → RA={ra:.6f}, Dec={dec:.6f}")

        # Controllo copertura ZTF
        if dec < -30:
            return jsonify({
                'success': False,
                'error': 'Stella fuori dalla copertura ZTF (Dec deve essere > -30°)',
                'gaia_id': gaia_id,
                'ra': ra,
                'dec': dec
            }), 404

        # Step 2: Query IRSA (senza BAD_CATFLAGS_MASK, filtriamo catflags==0 lato Python)
        logger.info(f"[ZTF Import] Querying IRSA at RA={ra:.6f}, Dec={dec:.6f}, radius={ZTF_DEFAULT_RADIUS_DEG}")
        params = {
            "POS": f"CIRCLE {ra} {dec} {ZTF_DEFAULT_RADIUS_DEG}",
            "BANDNAME": "g,r,i",
            "FORMAT": "csv",
        }

        try:
            resp = requests.get(IRSA_LIGHTCURVES_URL, params=params, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            content = resp.text.strip()
        except requests.Timeout:
            return jsonify({'error': 'Timeout connessione IRSA/ZTF'}), 504
        except requests.RequestException as e:
            return jsonify({'error': f'Errore connessione IRSA: {e}'}), 502

        if not content or content.startswith('<!DOCTYPE') or 'No data found' in content:
            return jsonify({
                'success': False,
                'error': 'Nessun dato ZTF trovato per questa stella',
                'gaia_id': gaia_id,
                'ra': ra,
                'dec': dec
            }), 404

        # Step 3: Parse CSV e filtra catflags==0
        lines = [l for l in content.splitlines() if not l.startswith('#')]
        cleaned_text = '\n'.join(lines)
        if not cleaned_text.strip():
            return jsonify({'success': False, 'error': 'Risposta ZTF vuota'}), 404

        df_raw = pd.read_csv(io.StringIO(cleaned_text))
        if df_raw.empty:
            return jsonify({'success': False, 'error': 'Nessun dato nella risposta ZTF'}), 404

        # Filtra catflags==0 (solo dati "good", come da riferimento utente)
        if 'catflags' in df_raw.columns:
            df_raw = df_raw.loc[df_raw['catflags'] == 0]
            logger.info(f"[ZTF Import] Dopo filtro catflags==0: {len(df_raw)} punti")

        if df_raw.empty:
            return jsonify({
                'success': False,
                'error': 'Nessun dato ZTF con catflags==0 (tutti i punti filtrati)',
                'gaia_id': gaia_id
            }), 404

        # Step 4: Crea import record
        import_record = create_import_record(
            db=db,
            catalog_name='ZTF',
            search_type='gaia_id',
            search_value=str(gaia_id),
            ra=ra,
            dec=dec,
            radius_arcsec=ZTF_DEFAULT_RADIUS_DEG * 3600,
            gaia_id=str(gaia_id),
            user_id=current_user.id,
            state='importing'
        )

        # Determina proprietario
        association_id_owner = None
        if current_user.role != 'superuser':
            association_id_owner = current_user.association_id

        # Step 5: Inserisci dati separati per filtro (ZTFr, ZTFg, ZTFi)
        total_points = 0
        bands = {}

        required_cols = ['hjd', 'mag']
        has_hjd = 'hjd' in df_raw.columns
        has_mjd = 'mjd' in df_raw.columns
        has_mag = 'mag' in df_raw.columns
        has_filtercode = 'filtercode' in df_raw.columns

        if not has_mag or (not has_hjd and not has_mjd):
            import_record.state = 'failed'
            import_record.error_message = 'Colonne hjd/mjd o mag mancanti nella risposta ZTF'
            db.commit()
            return jsonify({'success': False, 'error': 'Colonne necessarie mancanti nella risposta ZTF'}), 400

        # Converti MJD → HJD se necessario
        if has_hjd:
            time_col = df_raw['hjd']
        else:
            time_col = normalize_time(df_raw['mjd'], 'mjd')

        if has_filtercode:
            filter_groups = df_raw.groupby('filtercode')
        else:
            filter_groups = [('zr', df_raw)]  # Default a 'zr' se manca filtercode

        for filtercode, group_df in filter_groups:
            catalogo_name = ZTF_FILTER_MAP.get(filtercode, f'ZTF{filtercode}')

            # Prepara DataFrame per insert_catalog_data
            insert_df = pd.DataFrame({
                'hjd': time_col.loc[group_df.index] if has_hjd else normalize_time(group_df['mjd'], 'mjd'),
                'mag': group_df['mag'],
            })
            insert_df = insert_df.dropna(subset=['hjd', 'mag'])

            if insert_df.empty:
                continue

            points = insert_catalog_data(
                db=db,
                gaia_id=str(gaia_id),
                catalog_name=catalogo_name,
                data=insert_df,
                association_id_owner=association_id_owner,
                catalog_import_id=import_record.id
            )

            total_points += points
            bands[catalogo_name] = points
            logger.info(f"[ZTF Import] {catalogo_name}: {points} punti inseriti")

        if total_points == 0:
            import_record.state = 'failed'
            import_record.error_message = 'Nessun punto valido da inserire'
            db.commit()
            return jsonify({'success': False, 'error': 'Nessun punto ZTF valido da importare'}), 400

        # Step 6: Finalizza import record
        import_record.total_points_imported = total_points
        import_record.state = 'completed'

        # Link a progetto esistente
        existing_project = None
        if current_user.role == 'superuser':
            existing_project = db.query(Project).filter(
                Project.gaia_id == str(gaia_id),
                Project.state != 'cancelled'
            ).first()
        else:
            existing_project = db.query(Project).filter(
                Project.gaia_id == str(gaia_id),
                Project.association_id == current_user.association_id,
                Project.state != 'cancelled'
            ).first()

        if existing_project:
            import_record.project_id = existing_project.id
            import_record.target_association_id = existing_project.association_id

        db.commit()

        # Calcola statistiche per la risposta
        all_mags = df_raw['mag'].dropna()
        all_hjd = time_col.dropna() if has_hjd else normalize_time(df_raw['mjd'].dropna(), 'mjd')

        response = {
            'success': True,
            'catalog': 'ZTF',
            'gaia_id': str(gaia_id),
            'ra': ra,
            'dec': dec,
            'import_id': import_record.id,
            'total_points': total_points,
            'bands': bands,
            'time_range': {
                'min': float(all_hjd.min()) if len(all_hjd) > 0 else None,
                'max': float(all_hjd.max()) if len(all_hjd) > 0 else None,
                'span_days': float(all_hjd.max() - all_hjd.min()) if len(all_hjd) > 1 else 0,
            },
            'mag_range': {
                'min': float(all_mags.min()) if len(all_mags) > 0 else None,
                'max': float(all_mags.max()) if len(all_mags) > 0 else None,
            },
            'message': f'Importati {total_points} punti ZTF ({", ".join(f"{k}: {v}" for k, v in bands.items())})'
        }

        if existing_project:
            response['project_id'] = existing_project.id
            response['project_code'] = existing_project.project_code

        logger.info(f"[ZTF Import] Completato: {total_points} punti per Gaia {gaia_id}")
        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"[ZTF Import] Error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'ZTF'}), 500
    finally:
        try:
            db.close()
        except Exception:
            pass


@catalogs_bp.route('/api/catalogs/ztf/info')
@login_required
@admin_required('analyst')
def ztf_info():
    """
    Info sul catalogo ZTF
    """
    return jsonify({
        'catalog': 'ZTF',
        'name': 'Zwicky Transient Facility',
        'source': 'IRSA (Caltech)',
        'url': 'https://irsa.ipac.caltech.edu',
        'coverage': 'Dec > -30 gradi (emisfero nord)',
        'bands': ['g', 'r', 'i'],
        'cadence': '~3 giorni tipicamente',
        'depth': 'mag ~20-21',
        'time_format': 'MJD (convertito in HJD)',
        'notes': 'Usa BAD_CATFLAGS_MASK per filtrare dati di bassa qualità'
    })


# =============================================================================
# FUNZIONE HELPER GAIA ID
# =============================================================================

def resolve_gaia_id_by_source_id(gaia_id: str) -> Optional[dict]:
    """
    Risolve le coordinate di un Gaia source_id usando TAP query diretta.
    """
    return resolve_gaia_coordinates(gaia_id)
