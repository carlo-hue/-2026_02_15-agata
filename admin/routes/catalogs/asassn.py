# agata/admin/routes/catalogs/asassn.py
"""
Endpoint per catalogo ASAS-SN (All-Sky Automated Survey for Supernovae).

ASAS-SN fornisce dati fotometrici all-sky in banda V e g.
Survey tutto cielo, profondita' ~V17.

API: https://asas-sn.osu.edu/
Sky Patrol: https://asas-sn.osu.edu/photometry

Caratteristiche ASAS-SN:
- Copertura: Tutto cielo
- Bande: V (storica), g (attuale)
- Cadenza: ~2-3 giorni
- Profondita: V ~17 mag
- Database: 10+ anni di osservazioni
- Note: L'API pubblica ha rate limiting
"""
import logging
import requests
import pandas as pd
import io
from typing import Optional, Tuple

from flask import request, jsonify
from flask_login import login_required, current_user

from . import catalogs_bp
from .common import (
    get_db_session,
    validate_coordinates,
    resolve_gaia_coordinates,
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
# CONFIGURAZIONE ASAS-SN
# =============================================================================

# API endpoints ASAS-SN Sky Patrol V2.0
# Documentazione: http://asas-sn.ifa.hawaii.edu/documentation/pyasassn.html
ASASSN_MASTER_LIST_URL = "https://asas-sn.ifa.hawaii.edu/api/v0.1/master_list"
ASASSN_LIGHTCURVE_URL = "https://asas-sn.ifa.hawaii.edu/api/v0.1/light_curve"

# Timeout per fase (lightcurve può essere grande e lenta)
TIMEOUT_MASTER_LIST = 30  # Cone search veloce
TIMEOUT_LIGHTCURVE = 300  # Download lightcurve può essere lento (default 300s = 5min)


# =============================================================================
# FUNZIONI SPECIFICHE ASAS-SN
# =============================================================================

def _query_asassn_lightcurve(
    ra: float,
    dec: float,
    radius_arcsec: float = 5.0
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Query ASAS-SN Sky Patrol V2.0 via REST API.

    Workflow:
    1. Query master_list per trovare sorgente più vicina (cone search)
    2. Scarica lightcurve della sorgente trovata

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        radius_arcsec: raggio di ricerca in arcsec (default 5")

    Returns:
        Tuple (DataFrame, error_message)
        DataFrame con colonne standard: [hjd, mag, mag_err]
    """

    try:
        # Step 1: Cone search nel master list
        # Cerchiamo sorgenti entro il raggio specificato
        master_list_params = {
            'ra': ra,
            'dec': dec,
            'radius': radius_arcsec / 3600.0,  # Converte arcsec in gradi
        }

        logger.info(f"ASAS-SN [Step 1/3]: cone search master_list (RA={ra:.6f}, Dec={dec:.6f}, radius={radius_arcsec}\")")
        resp_master = requests.get(
            ASASSN_MASTER_LIST_URL,
            params=master_list_params,
            timeout=TIMEOUT_MASTER_LIST
        )
        resp_master.raise_for_status()
        logger.info(f"ASAS-SN [Step 1/3]: master_list response OK ({len(resp_master.text)} bytes)")

        data_master = resp_master.json()

        # Verifica se ci sono risultati
        if not data_master or 'results' not in data_master or len(data_master['results']) == 0:
            return None, "Nessuna sorgente ASAS-SN trovata nel raggio specificato"

        # Prendi la sorgente più vicina (primo risultato)
        source = data_master['results'][0]
        asas_sn_id = source.get('name') or source.get('asas_sn_id')

        if not asas_sn_id:
            return None, "ID ASAS-SN non trovato nei risultati"

        logger.info(f"ASAS-SN [Step 2/3]: trovata sorgente {asas_sn_id}, downloading lightcurve...")

        # Step 2: Scarica lightcurve della sorgente
        lc_params = {'name': asas_sn_id}

        resp_lc = requests.get(
            ASASSN_LIGHTCURVE_URL,
            params=lc_params,
            timeout=TIMEOUT_LIGHTCURVE
        )
        resp_lc.raise_for_status()
        logger.info(f"ASAS-SN [Step 2/3]: lightcurve downloaded ({len(resp_lc.text)} bytes)")

        # Scarica come CSV
        csv_text = resp_lc.text

        if not csv_text or len(csv_text) < 50:
            return None, "Lightcurve ASAS-SN vuota o non valida"

        logger.info(f"ASAS-SN [Step 2/2 complete]: CSV downloaded successfully ({len(csv_text)} bytes)")

    except requests.exceptions.ConnectTimeout:
        msg = f"ASAS-SN API: timeout connessione (>{TIMEOUT_MASTER_LIST}s per master_list)"
        logger.error(msg)
        return None, msg
    except requests.exceptions.ReadTimeout:
        msg = f"ASAS-SN API: timeout download (>{TIMEOUT_LIGHTCURVE}s per lightcurve)"
        logger.error(msg)
        return None, msg
    except requests.exceptions.Timeout:
        msg = f"ASAS-SN API: timeout generico"
        logger.error(msg)
        return None, msg
    except requests.exceptions.ConnectionError as e:
        msg = f"ASAS-SN: errore connessione ({str(e)[:100]})"
        logger.error(msg)
        return None, msg
    except requests.exceptions.RequestException as e:
        msg = f"ASAS-SN: errore HTTP ({str(e)[:100]})"
        logger.error(msg)
        return None, msg
    except Exception as e:
        logger.error("Errore query ASAS-SN Sky Patrol (HTTP phase)", exc_info=True)
        return None, f"Errore ASAS-SN: {str(e)[:100]}"

    # ==== STEP 3: Parsing e elaborazione CSV (fuori dal try-except delle richieste HTTP) ====
    try:
        logger.info(f"ASAS-SN [Step 3/3]: parsing CSV ({len(csv_text)} bytes)...")
        df = pd.read_csv(io.StringIO(csv_text))
        logger.info(f"ASAS-SN [Step 3/3]: CSV parsed, {len(df)} righe totali")

        if df.empty:
            return None, "Nessun dato nella lightcurve ASAS-SN"

        # Normalizza nomi colonne
        logger.info(f"ASAS-SN [Step 3/3]: normalizing columns...")
        df.columns = df.columns.str.lower().str.strip()
        logger.info(f"Colonne: {df.columns.tolist()}")

        # Verifica colonne minime
        if "hjd" not in df.columns or "mag" not in df.columns:
            logger.error(f"Colonne mancanti. Disponibili: {df.columns.tolist()}")
            return None, "Formato dati ASAS-SN non riconosciuto (colonne hjd/mag mancanti)"

        logger.info(f"ASAS-SN [Step 3/3]: filtering data (mag < 90, dropna)...")
        # Pulizia dati: mag = 99.99 → non-detection
        df = df[df["mag"] < 90].copy()
        df = df.dropna(subset=["hjd", "mag"])
        logger.info(f"ASAS-SN [Step 3/3]: after filtering, {len(df)} rows remain")

        if df.empty:
            return None, "Nessun dato valido dopo pulizia ASAS-SN"

        logger.info(f"ASAS-SN [Step 3/3]: converting to float and creating result...")
        # Standardizza output
        result = pd.DataFrame({
            "hjd": df["hjd"].astype(float),
            "mag": df["mag"].astype(float),
        })

        # Aggiungi errori se disponibili
        if "mag_err" in df.columns:
            result["mag_err"] = df["mag_err"].astype(float)
        elif "magerr" in df.columns:
            result["mag_err"] = df["magerr"].astype(float)

        logger.info(f"ASAS-SN [Step 3/3]: sorting by hjd...")
        result = result.sort_values("hjd").reset_index(drop=True)

        logger.info(
            f"ASAS-SN V2.0 SUCCESS: {len(result)} punti fotometrici per {asas_sn_id} "
            f"(RA={ra:.6f}, Dec={dec:.6f})"
        )

        return result, None

    except Exception as e:
        logger.error(f"ASAS-SN [Step 3/3]: ERROR: {type(e).__name__}: {str(e)[:200]}", exc_info=True)
        return None, f"Errore elaborazione dati ASAS-SN: {str(e)[:100]}"



# =============================================================================
# ENDPOINT ASAS-SN
# =============================================================================

@catalogs_bp.route('/api/catalogs/asassn/search', methods=['POST'])
@login_required
@admin_required('analyst')  # Analyst può cercare per stelle assegnate
def search_asassn():
    """
    Ricerca dati ASAS-SN per coordinate.

    Workflow:
    1. Valida coordinate
    2. Query Sky Patrol per lightcurve
    3. Parse CSV response (rimuovi non-detection mag=99.99)
    4. Crea record CatalogImport
    5. Restituisce preview

    Body JSON:
    - ra: float (gradi, 0-360)
    - dec: float (gradi, -90 to +90)
    - gaia_id: str (opzionale)

    Note: ASAS-SN non usa radius, fa match sulla posizione

    Returns:
        JSON con import_id, point_count, preview_data
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    # Validazione coordinate
    valid, error, ra, dec = validate_coordinates(data.get('ra'), data.get('dec'))
    if not valid:
        return jsonify({'error': error}), 400

    input_gaia_id = data.get('gaia_id')

    db = get_db_session()
    try:
        logger.info(f"ASAS-SN search: RA={ra}, Dec={dec}")

        # Step 1: Query ASAS-SN
        df, query_error = _query_asassn_lightcurve(ra, dec)

        # Step 2: Risolvi Gaia ID se non fornito
        gaia_id = input_gaia_id
        if not gaia_id:
            gaia_info = resolve_gaia_id(ra, dec, 10.0)
            if gaia_info:
                gaia_id = gaia_info['source_id']
                logger.info(f"Gaia ID risolto: {gaia_id}")

        # Step 3: Crea record import
        search_value = input_gaia_id if input_gaia_id else f"{ra:.6f},{dec:.6f}"
        search_type = 'gaia_id' if input_gaia_id else 'coordinates'

        import_record = create_import_record(
            db=db,
            catalog_name='ASAS-SN',
            search_type=search_type,
            search_value=search_value,
            ra=ra,
            dec=dec,
            radius_arcsec=0,  # ASAS-SN non usa radius
            gaia_id=gaia_id,
            user_id=current_user.id
        )

        # Step 4: Gestisci risultato
        if df is None or df.empty:
            update_import_with_results(
                db=db,
                import_record=import_record,
                catalog_name='ASAS-SN',
                success=False,
                point_count=0,
                error_message=query_error or "Nessun dato trovato"
            )
            return jsonify({
                'success': False,
                'catalog': 'ASAS-SN',
                'import_id': import_record.id,
                'error': query_error or "Nessun dato ASAS-SN trovato",
                'gaia_id': gaia_id
            }), 404

        # Calcola statistiche
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        # Aggiorna record con risultati
        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name='ASAS-SN',
            success=True,
            point_count=len(df),
            band='V',  # ASAS-SN banda predominante
            time_range=time_range,
            mag_range=mag_range
        )

        # Preview: prime 100 righe
        preview_data = df.head(100).to_dict(orient='records')

        return jsonify({
            'success': True,
            'catalog': 'ASAS-SN',
            'import_id': import_record.id,
            'point_count': len(df),
            'gaia_id': gaia_id,
            'band': 'V',
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
            'message': f"Trovati {len(df)} punti ASAS-SN (banda V)"
        })

    except Exception as e:
        db.rollback()
        logger.error(f"ASAS-SN search error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'ASAS-SN'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/asassn/import/<int:import_id>', methods=['POST'])
@login_required
@admin_required('analyst')  # Analyst può aggiungere dati a stelle esistenti
def import_asassn(import_id: int):
    """
    Importa dati ASAS-SN in database.

    Ri-esegue la query ASAS-SN e inserisce i dati in Cataloghi_esterni.

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
                    'catalog': 'ASAS-SN'
                }), 403
            auto_create_project = True

        # Aggiorna stato
        import_record.resolved_gaia_id = gaia_id
        import_record.state = 'importing'
        db.commit()

        # Ri-esegui query
        df, query_error = _query_asassn_lightcurve(
            import_record.resolved_ra,
            import_record.resolved_dec
        )

        if df is None or df.empty:
            import_record.state = 'failed'
            import_record.error_message = query_error or "Nessun dato nella ri-query"
            db.commit()
            return jsonify({
                'success': False,
                'error': query_error or "Nessun dato ASAS-SN nella ri-query",
                'catalog': 'ASAS-SN'
            }), 400

        # Inserisci dati
        points_imported = insert_catalog_data(
            db, gaia_id, 'ASAS-SN', df,
            catalog_import_id=import_record.id
        )

        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({
                'success': False,
                'error': "Nessun punto importato in database",
                'catalog': 'ASAS-SN'
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
            catalog_name='ASAS-SN'
        )

        if not success:
            return jsonify({'error': error, 'catalog': 'ASAS-SN'}), 400

        response = {
            'success': True,
            'catalog': 'ASAS-SN',
            'import_id': import_id,
            'points_imported': points_imported,
            'gaia_id': gaia_id,
            'message': f'Importati {points_imported} punti ASAS-SN'
        }

        if created_project:
            response['project_created'] = True
            response['project_id'] = created_project.id
            response['project_code'] = created_project.project_code
            response['message'] += f' - Creato progetto {created_project.project_code}'

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"ASAS-SN import error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'catalog': 'ASAS-SN'}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/asassn/info')
@login_required
@admin_required('analyst')
def asassn_info():
    """
    Informazioni sul catalogo ASAS-SN.

    Returns:
        JSON con descrizione e caratteristiche
    """
    return jsonify({
        'catalog': 'ASAS-SN',
        'name': 'All-Sky Automated Survey for Supernovae',
        'source': 'Ohio State University',
        'url': 'https://asas-sn.osu.edu',
        'coverage': 'Tutto cielo',
        'bands': ['V (storica)', 'g (attuale)'],
        'cadence': '~2-3 giorni',
        'depth': 'V ~17 mag',
        'time_format': 'HJD',
        'notes': 'API pubblica con rate limiting. mag=99.99 indica non-detection.'
    })


# =============================================================================
# DOWNLOAD AUTOMATICO ASAS-SN (analogo a TESS QLP)
# =============================================================================

@catalogs_bp.route('/api/catalogs/asassn/auto/search-data', methods=['POST'])
@login_required
@admin_required('analyst')
def asassn_auto_search():
    """
    Cerca dati ASAS-SN automaticamente partendo da Gaia ID o project_id.

    Workflow:
    1. Gaia ID → Coordinate (da database o Gaia Archive)
    2. Coordinate → Query ASAS-SN Sky Patrol
    3. Restituisci preview con statistiche

    Body JSON:
    - gaia_id: str (per superuser) oppure
    - project_id: int (per admin/analyst)

    Returns:
        JSON con success, data_available, point_count, time_range, mag_range, gaia_id
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    gaia_id = data.get('gaia_id')
    project_id = data.get('project_id')

    if not gaia_id and not project_id:
        return jsonify({'error': 'Specificare gaia_id o project_id'}), 400

    db = get_db_session()

    try:
        # Recupera gaia_id da project_id se necessario
        if project_id and not gaia_id:
            from .tess import get_gaia_id_from_project
            logger.info(f"Admin/Analyst request: retrieving Gaia ID from project_id={project_id}")
            user_assoc = None if current_user.role == 'superuser' else current_user.association_id
            gaia_id = get_gaia_id_from_project(db, project_id, user_assoc)
            if not gaia_id:
                logger.warning(f"Project {project_id} not found or not accessible for user {current_user.id}")
                return jsonify({'error': f'Project {project_id} non trovato o non accessibile'}), 404
            logger.info(f"Retrieved Gaia ID {gaia_id} from project {project_id}")

        logger.info(f"Starting ASAS-SN auto-search for Gaia {gaia_id}")

        # Step 1: Risolvi coordinate da Gaia ID
        gaia_info = resolve_gaia_coordinates(gaia_id)
        if not gaia_info:
            return jsonify({'error': f'Impossibile risolvere coordinate per Gaia {gaia_id}'}), 404

        ra = gaia_info['ra']
        dec = gaia_info['dec']
        logger.info(f"Resolved Gaia {gaia_id} → RA={ra:.6f}, Dec={dec:.6f}")

        # Step 2: Query ASAS-SN
        df, query_error = _query_asassn_lightcurve(ra, dec)

        if df is None or df.empty:
            logger.warning(f"No ASAS-SN data found for Gaia {gaia_id} (RA={ra}, Dec={dec})")
            return jsonify({
                'success': True,
                'data_available': False,
                'gaia_id': gaia_id,
                'ra': ra,
                'dec': dec,
                'error': query_error or "Nessun dato ASAS-SN disponibile per questa stella",
                'message': 'Nessun dato ASAS-SN trovato'
            }), 404

        # Step 3: Calcola statistiche
        time_range = {
            'min': float(df['hjd'].min()),
            'max': float(df['hjd'].max()),
            'span_days': float(df['hjd'].max() - df['hjd'].min())
        }
        mag_range = {
            'min': float(df['mag'].min()),
            'max': float(df['mag'].max())
        }

        logger.info(f"Found {len(df)} ASAS-SN points for Gaia {gaia_id}")

        response = {
            'success': True,
            'data_available': True,
            'gaia_id': gaia_id,
            'ra': ra,
            'dec': dec,
            'point_count': len(df),
            'band': 'V',
            'time_range': time_range,
            'mag_range': mag_range,
            'message': f'Trovati {len(df)} punti ASAS-SN (banda V)'
        }

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"Error in asassn_auto_search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db.close()
        except Exception:
            pass


@catalogs_bp.route('/api/catalogs/asassn/auto/download-data', methods=['POST'])
@login_required
@admin_required('analyst')
def asassn_auto_download():
    """
    Scarica e importa automaticamente dati ASAS-SN nel database.

    Workflow:
    1. Risolvi coordinate da Gaia ID
    2. Query ASAS-SN Sky Patrol
    3. Crea CatalogImport record
    4. Insert data in Cataloghi_esterni
    5. Link a progetto esistente se disponibile

    Body JSON:
    - gaia_id: str (per superuser) oppure
    - project_id: int (per admin/analyst)

    Returns:
        JSON con success, import_id, points_imported, project_id (se linkato)
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    gaia_id = data.get('gaia_id')
    project_id = data.get('project_id')

    if not gaia_id and not project_id:
        return jsonify({'error': 'Specificare gaia_id o project_id'}), 400

    db = get_db_session()

    try:
        # Recupera gaia_id da project_id se necessario
        if project_id and not gaia_id:
            from .tess import get_gaia_id_from_project
            logger.info(f"Admin/Analyst request: retrieving Gaia ID from project_id={project_id}")
            user_assoc = None if current_user.role == 'superuser' else current_user.association_id
            gaia_id = get_gaia_id_from_project(db, project_id, user_assoc)
            if not gaia_id:
                logger.warning(f"Project {project_id} not found or not accessible for user {current_user.id}")
                return jsonify({'error': f'Project {project_id} non trovato o non accessibile'}), 404
            logger.info(f"Retrieved Gaia ID {gaia_id} from project {project_id}")

        logger.info(f"Starting ASAS-SN auto-download for Gaia {gaia_id}")

        # Step 1: Risolvi coordinate
        gaia_info = resolve_gaia_coordinates(gaia_id)
        if not gaia_info:
            return jsonify({'error': f'Impossibile risolvere coordinate per Gaia {gaia_id}'}), 404

        ra = gaia_info['ra']
        dec = gaia_info['dec']

        # Step 2: Crea import record
        import_record = create_import_record(
            db=db,
            catalog_name='ASAS-SN',
            search_type='gaia_id',
            search_value=f"Gaia {gaia_id}",
            ra=ra,
            dec=dec,
            radius_arcsec=0,
            gaia_id=gaia_id,
            user_id=current_user.id,
            state='importing'
        )

        # Step 3: Query ASAS-SN
        df, query_error = _query_asassn_lightcurve(ra, dec)

        if df is None or df.empty:
            import_record.state = 'failed'
            import_record.error_message = query_error or "Nessun dato ASAS-SN disponibile"
            db.commit()
            return jsonify({
                'success': False,
                'error': query_error or "Nessun dato ASAS-SN disponibile per questa stella",
                'import_id': import_record.id
            }), 404

        # Step 4: Insert data
        association_id_owner = None
        if current_user.role != 'superuser':
            association_id_owner = current_user.association_id

        points_imported = insert_catalog_data(
            db, gaia_id, 'ASAS-SN', df,
            association_id_owner=association_id_owner,
            catalog_import_id=import_record.id
        )

        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({
                'success': False,
                'error': "Nessun punto importato (dati presenti ma non validi)",
                'import_id': import_record.id
            }), 404

        # Step 5: Aggiorna import record
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name='ASAS-SN',
            success=True,
            point_count=points_imported,
            band='V',
            time_range=time_range,
            mag_range=mag_range
        )

        import_record.total_points_imported = points_imported
        from datetime import datetime
        import_record.completed_at = datetime.utcnow()
        db.commit()

        # Step 6: Link a progetto esistente
        from agata.auth_models import Project
        existing_project = None
        if current_user.role == 'superuser':
            existing_project = db.query(Project).filter(
                Project.gaia_id == gaia_id,
                Project.state != 'cancelled'
            ).first()
        else:
            existing_project = db.query(Project).filter(
                Project.gaia_id == gaia_id,
                Project.association_id == current_user.association_id,
                Project.state != 'cancelled'
            ).first()

        result = {
            'success': True,
            'import_id': import_record.id,
            'points_imported': points_imported,
            'gaia_id': gaia_id,
            'catalog': 'ASAS-SN',
            'band': 'V',
            'time_range': {
                'min': time_range[0],
                'max': time_range[1]
            },
            'mag_range': {
                'min': mag_range[0],
                'max': mag_range[1]
            },
            'message': f'Importati {points_imported} punti ASAS-SN'
        }

        if existing_project:
            import_record.project_id = existing_project.id
            import_record.target_association_id = existing_project.association_id
            db.commit()
            logger.info(f"Import {import_record.id} linkato al progetto {existing_project.project_code}")
            result['project_id'] = existing_project.id
            result['project_code'] = existing_project.project_code
        else:
            if current_user.role == 'superuser':
                logger.info(f"Superuser: nessun progetto per {gaia_id}, dati importati nel bacino centrale")
            else:
                logger.info(f"Nessun progetto per {gaia_id} nell'associazione {current_user.association_id}")

        return jsonify(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error in asassn_auto_download: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db.close()
        except Exception:
            pass
