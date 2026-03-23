# agata/admin/routes/catalogs/ogle.py
"""
Endpoint per catalogo OGLE (Optical Gravitational Lensing Experiment).

OGLE fornisce lightcurve per stelle variabili in Bulge, LMC, SMC.
Accesso via OCVS (OGLE Collection of Variable Stars).

API: http://ogledb.astrouw.edu.pl/~ogle/OCVS

Caratteristiche OGLE:
- Copertura: Bulge Galattico, LMC, SMC (aree specifiche)
- Bande: I (principale), V
- Cadenza: variabile (survey fotometrico)
- Profondita: I ~21 mag
- Tipi variabili: Cefeidi, RR Lyrae, Eclissanti, LPV
"""
import re
import logging
import requests
import pandas as pd
from typing import Optional, Tuple

from flask import request, jsonify
from flask_login import login_required, current_user

from . import catalogs_bp
from .common import (
    get_db_session,
    validate_coordinates,
    resolve_gaia_id,
    create_import_record,
    update_import_with_results,
    insert_catalog_data,
    finalize_import,
    get_import_record,
    can_create_new_star,
    can_add_data_to_star,
)
from agata.admin.decorators import admin_required

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAZIONE OGLE
# =============================================================================

OGLE_BASE_URL = "http://ogledb.astrouw.edu.pl/~ogle"
OGLE_OCVS_URL = "https://ogledb.astrouw.edu.pl/~ogle/OCVS"
OGLE_QUERY_URL = f"{OGLE_OCVS_URL}/catalog_query.php"
TIMEOUT_SECONDS = 90

# Regioni di copertura OGLE
COVERAGE_REGIONS = [
    {'name': 'Bulge', 'ra_range': (255, 280), 'dec_range': (-35, -20)},
    {'name': 'LMC', 'ra_range': (66, 91), 'dec_range': (-73, -65)},
    {'name': 'SMC', 'ra_range': (5, 20), 'dec_range': (-75, -70)},
]


# =============================================================================
# FUNZIONI SPECIFICHE OGLE
# =============================================================================

def _get_coverage_region(ra: float, dec: float) -> Optional[str]:
    """
    Verifica se le coordinate sono nella copertura OGLE.

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi

    Returns:
        Nome regione (Bulge, LMC, SMC) o None se fuori copertura
    """
    for region in COVERAGE_REGIONS:
        ra_min, ra_max = region['ra_range']
        dec_min, dec_max = region['dec_range']
        if ra_min <= ra <= ra_max and dec_min <= dec <= dec_max:
            return region['name']
    return None


def _query_ogle_catalog(ra: float, dec: float, radius_arcmin: float = 5) -> Tuple[Optional[str], Optional[str]]:
    """
    Query al catalogo OCVS per trovare stelle variabili.

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        radius_arcmin: Raggio ricerca in arcominuti

    Returns:
        Tuple (star_id, error_message)
        star_id e' nel formato OGLE-XXX-YYY-NNNN
    """
    radius_arcsec = int(radius_arcmin * 60)

    # Costruisci payload per query spaziale
    payload = {
        "qtype": "pos",
        "use_target": "on",
        "val_targetLMC": "on",
        "val_targetSMC": "on",
        "val_targetBLG": "on",
        "use_ra": "on",
        "valmin_ra": f"{ra:.5f} r{radius_arcsec} {dec:.5f}",
        "use_type": "on",
        "val_typeCep": "on",
        "val_typeRRLyr": "on",
        "val_typeECL": "on",
        "val_typeLPV": "on",
        "out": "html",
        "submit": "Submit"
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
        'Referer': OGLE_QUERY_URL,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        logger.info(f"OGLE query: RA={ra}, Dec={dec}, radius={radius_arcmin} arcmin")

        resp = requests.post(
            OGLE_QUERY_URL,
            data=payload,
            headers=headers,
            timeout=TIMEOUT_SECONDS
        )
        resp.raise_for_status()

        # Cerca ID stella nel risultato HTML
        if "OGLE-" not in resp.text:
            return None, "Nessuna stella variabile trovata in questa regione"

        # Estrai tutti gli ID trovati
        ids = re.findall(r'OGLE-[A-Z0-9]+-[A-Z0-9]+-\d+', resp.text)
        if not ids:
            return None, "Nessun ID stella estratto dalla risposta"

        # Prendi il primo ID (o preferisci quello della regione corretta)
        region = _get_coverage_region(ra, dec)
        if region:
            # Cerca un ID che corrisponda alla regione
            for star_id in ids:
                if region[:3].upper() in star_id:
                    return star_id, None

        # Fallback: primo ID trovato
        return ids[0], None

    except requests.Timeout:
        return None, "Timeout connessione OGLE"
    except requests.RequestException as e:
        return None, f"Errore connessione OGLE: {str(e)}"
    except Exception as e:
        logger.error(f"OGLE catalog query error: {e}", exc_info=True)
        return None, str(e)


def _download_ogle_lightcurve(star_id: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Scarica lightcurve OGLE dal file .dat.

    Args:
        star_id: ID stella nel formato OGLE-XXX-YYY-NNNN

    Returns:
        Tuple (DataFrame con dati, error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
        'Referer': OGLE_OCVS_URL
    }

    # Prova diversi endpoint
    base_urls = [
        OGLE_OCVS_URL,
        f"{OGLE_BASE_URL}/OGLE_IV/OCVS"
    ]

    df = None
    for base_url in base_urls:
        dl_url = f"{base_url}/get_dat.php?stella={star_id}&band=I"
        try:
            resp = requests.get(dl_url, headers=headers, timeout=30)
            if resp.status_code == 200 and "<html>" not in resp.text[:200].lower():
                df = _parse_ogle_dat(resp.text)
                if df is not None and not df.empty:
                    return df, None
        except Exception as e:
            logger.warning(f"OGLE download from {base_url} failed: {e}")
            continue

    return None, f"Impossibile scaricare lightcurve per {star_id}"


def _parse_ogle_dat(content: str) -> Optional[pd.DataFrame]:
    """
    Parse file .dat OGLE in DataFrame.

    Formato tipico: HJD mag mag_err (separati da spazi)

    Args:
        content: Contenuto del file .dat

    Returns:
        DataFrame con colonne [hjd, mag, mag_err]
    """
    rows = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        try:
            hjd = float(parts[0])
            mag = float(parts[1])
            err = float(parts[2]) if len(parts) > 2 else None
            rows.append({"hjd": hjd, "mag": mag, "mag_err": err})
        except ValueError:
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["hjd", "mag"])
    df = df.sort_values("hjd").reset_index(drop=True)

    logger.info(f"OGLE: parsed {len(df)} punti fotometrici")
    return df


# =============================================================================
# ENDPOINT OGLE
# =============================================================================

@catalogs_bp.route('/api/catalogs/ogle/search', methods=['POST'])
@login_required
@admin_required('analyst')  # Analyst può cercare per stelle assegnate
def search_ogle():
    """
    Ricerca dati OGLE per coordinate.

    Workflow:
    1. Verifica che le coordinate siano nella copertura OGLE (Bulge, LMC, SMC)
    2. Query al catalogo OCVS per trovare stelle variabili
    3. Estrai ID stella dalla risposta HTML
    4. Scarica lightcurve dal file .dat
    5. Crea record CatalogImport con dati

    Body JSON:
    - ra: float (gradi, 0-360)
    - dec: float (gradi, -90 to +90)
    - radius_arcmin: float (default 5.0)
    - gaia_id: str (opzionale)

    Returns:
        JSON con import_id, star_id, point_count, preview_data
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    # Validazione coordinate
    valid, error, ra, dec = validate_coordinates(data.get('ra'), data.get('dec'))
    if not valid:
        return jsonify({'error': error}), 400

    # Verifica copertura OGLE
    region = _get_coverage_region(ra, dec)
    if region is None:
        return jsonify({
            'success': False,
            'catalog': 'OGLE',
            'error': 'Coordinate fuori dalla copertura OGLE. '
                     'OGLE copre: Bulge (RA 255-280, Dec -35 a -20), '
                     'LMC (RA 66-91, Dec -73 a -65), '
                     'SMC (RA 5-20, Dec -75 a -70)'
        }), 400

    radius_arcmin = float(data.get('radius_arcmin', 5.0))
    input_gaia_id = data.get('gaia_id')

    db = get_db_session()
    try:
        logger.info(f"OGLE search: RA={ra}, Dec={dec}, region={region}")

        # Step 1: Query catalogo OCVS
        star_id, query_error = _query_ogle_catalog(ra, dec, radius_arcmin)

        if star_id is None:
            # Risolvi comunque Gaia ID per il record
            gaia_id = input_gaia_id
            if not gaia_id:
                gaia_info = resolve_gaia_id(ra, dec, 10.0)
                if gaia_info:
                    gaia_id = gaia_info['source_id']

            # Crea record con errore
            search_value = input_gaia_id if input_gaia_id else f"{ra:.6f},{dec:.6f}"
            import_record = create_import_record(
                db=db,
                catalog_name='OGLE',
                search_type='gaia_id' if input_gaia_id else 'coordinates',
                search_value=search_value,
                ra=ra,
                dec=dec,
                radius_arcsec=radius_arcmin * 60,
                gaia_id=gaia_id,
                user_id=current_user.id
            )

            update_import_with_results(
                db=db,
                import_record=import_record,
                catalog_name='OGLE',
                success=False,
                point_count=0,
                error_message=query_error
            )

            return jsonify({
                'success': False,
                'catalog': 'OGLE',
                'import_id': import_record.id,
                'region': region,
                'error': query_error,
                'gaia_id': gaia_id
            }), 404

        logger.info(f"OGLE: trovata stella {star_id}")

        # Step 2: Scarica lightcurve
        df, download_error = _download_ogle_lightcurve(star_id)

        # Step 3: Risolvi Gaia ID
        gaia_id = input_gaia_id
        if not gaia_id:
            gaia_info = resolve_gaia_id(ra, dec, 10.0)
            if gaia_info:
                gaia_id = gaia_info['source_id']
                logger.info(f"Gaia ID risolto: {gaia_id}")

        # Step 4: Crea record import
        search_value = input_gaia_id if input_gaia_id else f"{ra:.6f},{dec:.6f}"
        import_record = create_import_record(
            db=db,
            catalog_name='OGLE',
            search_type='gaia_id' if input_gaia_id else 'coordinates',
            search_value=search_value,
            ra=ra,
            dec=dec,
            radius_arcsec=radius_arcmin * 60,
            gaia_id=gaia_id,
            user_id=current_user.id
        )

        # Step 5: Gestisci risultato
        if df is None or df.empty:
            update_import_with_results(
                db=db,
                import_record=import_record,
                catalog_name='OGLE',
                success=False,
                point_count=0,
                error_message=download_error or "Nessun dato nella lightcurve",
                source_id=star_id
            )

            return jsonify({
                'success': False,
                'catalog': 'OGLE',
                'import_id': import_record.id,
                'star_id': star_id,
                'region': region,
                'error': download_error or "Impossibile scaricare lightcurve",
                'gaia_id': gaia_id
            }), 404

        # Calcola statistiche
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name='OGLE',
            success=True,
            point_count=len(df),
            band='I',
            source_id=star_id,
            time_range=time_range,
            mag_range=mag_range
        )

        # Preview
        preview_data = df.head(100).to_dict(orient='records')

        return jsonify({
            'success': True,
            'catalog': 'OGLE',
            'import_id': import_record.id,
            'star_id': star_id,
            'region': region,
            'point_count': len(df),
            'gaia_id': gaia_id,
            'band': 'I',
            'time_range': {
                'min': time_range[0],
                'max': time_range[1],
                'span_days': time_range[1] - time_range[0]
            },
            'mag_range': {
                'min': mag_range[0],
                'max': mag_range[1]
            },
            'preview': preview_data,
            'message': f"Trovati {len(df)} punti OGLE per {star_id} (banda I)"
        })

    except Exception as e:
        db.rollback()
        logger.error(f"OGLE search error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'OGLE'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/ogle/import/<int:import_id>', methods=['POST'])
@login_required
@admin_required('analyst')  # Analyst può aggiungere dati a stelle esistenti
def import_ogle(import_id: int):
    """
    Importa dati OGLE in database.

    Ri-scarica la lightcurve OGLE e inserisce i dati in Cataloghi_esterni.

    Permessi:
    - superuser: può sempre importare (anche nuove stelle)
    - admin: può importare nuove stelle solo fino al limite dell'associazione
    - analyst: può aggiungere dati solo a stelle già nella propria associazione

    Body JSON:
    - gaia_id: str (obbligatorio)

    Returns:
        JSON con success, points_imported, project_info
    """
    data = request.get_json() or {}
    gaia_id = data.get('gaia_id')

    if not gaia_id:
        return jsonify({'error': 'gaia_id e obbligatorio'}), 400

    db = get_db_session()
    try:
        # Verifica permessi base
        import_record, error = get_import_record(
            db, import_id, current_user.id, current_user.role == 'superuser'
        )
        if error:
            return jsonify({'error': error}), 404 if 'non trovato' in error else 403

        if import_record.state not in ('preview', 'failed'):
            return jsonify({'error': f'Import non in stato preview (stato: {import_record.state})'}), 400

        # Verifica se l'utente può aggiungere dati a questa stella
        can_add, add_error, existing_project = can_add_data_to_star(
            db, gaia_id, current_user.role, current_user.association_id, current_user.id
        )

        # Se non può aggiungere dati a stella esistente, verifica se può creare nuova stella
        auto_create_project = False
        if not can_add:
            can_create, create_error = can_create_new_star(
                db, current_user.role, current_user.association_id
            )
            if not can_create:
                return jsonify({
                    'error': add_error or create_error,
                    'catalog': 'OGLE'
                }), 403
            auto_create_project = True

        # Recupera star_id dai risultati precedenti
        catalogs_queried = import_record.catalogs_queried or {}
        ogle_info = catalogs_queried.get('OGLE', {})
        star_id = ogle_info.get('source_id')

        if not star_id:
            # Ri-esegui query per trovare star_id
            star_id, query_error = _query_ogle_catalog(
                import_record.resolved_ra,
                import_record.resolved_dec,
                (import_record.search_radius_arcsec or 300) / 60  # Converti in arcmin
            )
            if not star_id:
                import_record.state = 'failed'
                import_record.error_message = query_error or "Star ID non trovato"
                db.commit()
                return jsonify({
                    'success': False,
                    'error': query_error or "Impossibile trovare stella OGLE",
                    'catalog': 'OGLE'
                }), 400

        # Aggiorna stato
        import_record.resolved_gaia_id = gaia_id
        import_record.state = 'importing'
        db.commit()

        # Scarica lightcurve
        df, download_error = _download_ogle_lightcurve(star_id)

        if df is None or df.empty:
            import_record.state = 'failed'
            import_record.error_message = download_error or "Nessun dato scaricato"
            db.commit()
            return jsonify({
                'success': False,
                'error': download_error or "Impossibile scaricare lightcurve OGLE",
                'catalog': 'OGLE'
            }), 400

        # Inserisci dati
        points_imported = insert_catalog_data(
            db, gaia_id, 'OGLE', df,
            catalog_import_id=import_record.id
        )

        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({
                'success': False,
                'error': "Nessun punto importato in database",
                'catalog': 'OGLE'
            }), 400

        # Finalizza
        association_id = None
        if auto_create_project and current_user.role == 'admin':
            association_id = current_user.association_id

        success, error, created_project = finalize_import(
            db=db,
            import_record=import_record,
            points_imported=points_imported,
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=association_id,
            auto_create_project=auto_create_project,
            catalog_name='OGLE'
        )

        if not success:
            return jsonify({'error': error, 'catalog': 'OGLE'}), 400

        response = {
            'success': True,
            'catalog': 'OGLE',
            'import_id': import_id,
            'star_id': star_id,
            'points_imported': points_imported,
            'gaia_id': gaia_id,
            'message': f'Importati {points_imported} punti OGLE per {star_id}'
        }

        if created_project:
            response['project_created'] = True
            response['project_id'] = created_project.id
            response['project_code'] = created_project.project_code
            response['message'] += f' - Creato progetto {created_project.project_code}'

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"OGLE import error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'OGLE'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/ogle/info')
@login_required
@admin_required('analyst')
def ogle_info():
    """
    Informazioni sul catalogo OGLE.

    Returns:
        JSON con descrizione, caratteristiche e copertura
    """
    return jsonify({
        'catalog': 'OGLE',
        'name': 'Optical Gravitational Lensing Experiment',
        'source': 'Warsaw University Observatory',
        'url': 'http://ogledb.astrouw.edu.pl',
        'coverage': {
            'Bulge': {'ra': '255-280 deg', 'dec': '-35 to -20 deg'},
            'LMC': {'ra': '66-91 deg', 'dec': '-73 to -65 deg'},
            'SMC': {'ra': '5-20 deg', 'dec': '-75 to -70 deg'}
        },
        'bands': ['I (principale)', 'V'],
        'variable_types': ['Cefeidi', 'RR Lyrae', 'Eclissanti', 'LPV'],
        'time_format': 'HJD',
        'notes': 'Copre solo regioni specifiche. Query via OCVS catalog.'
    })


@catalogs_bp.route('/api/catalogs/ogle/coverage')
@login_required
@admin_required('analyst')
def ogle_coverage():
    """
    Verifica se coordinate sono nella copertura OGLE.

    Query params:
    - ra: float
    - dec: float

    Returns:
        JSON con in_coverage e region
    """
    ra = request.args.get('ra')
    dec = request.args.get('dec')

    if not ra or not dec:
        return jsonify({'error': 'ra e dec sono obbligatori'}), 400

    try:
        ra_f = float(ra)
        dec_f = float(dec)
    except ValueError:
        return jsonify({'error': 'Coordinate non valide'}), 400

    region = _get_coverage_region(ra_f, dec_f)

    return jsonify({
        'ra': ra_f,
        'dec': dec_f,
        'in_coverage': region is not None,
        'region': region,
        'coverage_regions': COVERAGE_REGIONS
    })
