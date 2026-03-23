# agata/admin/routes/catalogs/file_upload.py
"""
Endpoint per caricamento dati fotometrici da file.

Permette di importare dati in formato CSV/TXT con colonne tempo/magnitudine.
Supporta auto-detection delle colonne e vari formati temporali.

Formati file supportati:
- CSV (comma-separated)
- TSV (tab-separated)
- Spazi come separatore

Formati tempo:
- HJD (Heliocentric Julian Date)
- JD (Julian Date)
- MJD (Modified Julian Date)
- BJD (Barycentric Julian Date)
- BTJD (TESS Barycentric Julian Date)
"""
import io
import logging
import pandas as pd
from typing import Optional, Tuple, List

from flask import request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import Session

from . import catalogs_bp
from .common import (
    get_db_session,
    resolve_gaia_id,
    create_import_record,
    update_import_with_results,
    insert_catalog_data,
    finalize_import,
    normalize_time,
    can_create_new_star,
    can_add_data_to_star,
)
from agata.admin.decorators import admin_required
from agata.auth_models import Project

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAZIONE FILE UPLOAD
# =============================================================================

# Nomi colonne comuni per auto-detection
TIME_COLUMN_ALIASES = ['hjd', 'jd', 'mjd', 'bjd', 'time', 'date', 't', 'epoch', 'btjd']
MAG_COLUMN_ALIASES = ['mag', 'magnitude', 'brightness', 'flux', 'm', 'vmag', 'rmag', 'gmag',
                      'mag_original', 'mag_detrended', 'imag', 'bmag']
ERR_COLUMN_ALIASES = ['mag_err', 'magerr', 'err', 'error', 'e_mag', 'sigma', 'uncertainty',
                      'mag_error', 'e_vmag', 'e_rmag']


# =============================================================================
# FUNZIONI DI PARSING FILE
# =============================================================================

def _detect_delimiter(sample_line: str) -> str:
    """
    Auto-detect delimiter da una linea di esempio.

    Args:
        sample_line: Linea di esempio dal file

    Returns:
        Carattere delimitatore
    """
    delimiters = [',', '\t', ';', ' ']
    counts = {d: sample_line.count(d) for d in delimiters}
    best = max(counts.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else ','


def _find_column(columns: List[str], aliases: List[str]) -> Optional[str]:
    """
    Trova colonna corrispondente agli alias.

    Args:
        columns: Lista nomi colonne nel file
        aliases: Lista alias da cercare

    Returns:
        Nome colonna trovata o None
    """
    columns_lower = [c.lower() for c in columns]
    for alias in aliases:
        if alias.lower() in columns_lower:
            idx = columns_lower.index(alias.lower())
            return columns[idx]
    return None


def _parse_file_content(
    content: str,
    time_col: Optional[str] = None,
    mag_col: Optional[str] = None,
    err_col: Optional[str] = None,
    time_format: str = 'hjd',
    delimiter: Optional[str] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Parse contenuto file in DataFrame standard.

    Args:
        content: Contenuto del file
        time_col: Nome colonna tempo (auto-detect se None)
        mag_col: Nome colonna magnitudine (auto-detect se None)
        err_col: Nome colonna errore (auto-detect se None)
        time_format: Formato tempo input
        delimiter: Delimitatore (auto-detect se None)

    Returns:
        Tuple (DataFrame con colonne [hjd, mag, mag_err], error_message)
    """
    try:
        # Rimuovi righe di commento
        lines = content.split('\n')
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
                clean_lines.append(line)

        if not clean_lines:
            return None, "Nessun dato valido nel file"

        cleaned_content = '\n'.join(clean_lines)

        # Auto-detect delimiter
        if delimiter is None:
            delimiter = _detect_delimiter(clean_lines[0] if clean_lines else "")

        # Parse CSV
        df = pd.read_csv(
            io.StringIO(cleaned_content),
            delimiter=delimiter,
            skipinitialspace=True
        )

        if df.empty:
            return None, "File vuoto"

        # Normalizza nomi colonne
        df.columns = [str(c).lower().strip() for c in df.columns]

        # Auto-detect colonne se non specificate
        if time_col is None:
            time_col = _find_column(df.columns, TIME_COLUMN_ALIASES)
            if time_col is None:
                return None, f"Colonna tempo non trovata. Colonne disponibili: {list(df.columns)}"
        else:
            time_col = time_col.lower().strip()

        if mag_col is None:
            mag_col = _find_column(df.columns, MAG_COLUMN_ALIASES)
            if mag_col is None:
                return None, f"Colonna magnitudine non trovata. Colonne disponibili: {list(df.columns)}"
        else:
            mag_col = mag_col.lower().strip()

        if err_col is None:
            err_col = _find_column(df.columns, ERR_COLUMN_ALIASES)
        elif err_col:
            err_col = err_col.lower().strip()

        # Verifica esistenza colonne
        if time_col not in df.columns:
            return None, f"Colonna tempo '{time_col}' non trovata"
        if mag_col not in df.columns:
            return None, f"Colonna magnitudine '{mag_col}' non trovata"

        # Costruisci DataFrame standard
        result_df = pd.DataFrame({
            'hjd': normalize_time(pd.to_numeric(df[time_col], errors='coerce'), time_format),
            'mag': pd.to_numeric(df[mag_col], errors='coerce'),
        })

        # Aggiungi errore se disponibile
        if err_col and err_col in df.columns:
            result_df['mag_err'] = pd.to_numeric(df[err_col], errors='coerce')

        # Rimuovi righe con valori non validi
        result_df = result_df.dropna(subset=['hjd', 'mag'])

        if result_df.empty:
            return None, "Nessun dato valido dopo il parsing"

        # Ordina per tempo
        result_df = result_df.sort_values('hjd').reset_index(drop=True)

        logger.info(f"File parsing: {len(result_df)} punti validi")

        return result_df, None

    except pd.errors.EmptyDataError:
        return None, "File vuoto o senza dati"
    except pd.errors.ParserError as e:
        return None, f"Errore parsing CSV: {str(e)}"
    except Exception as e:
        logger.error(f"Errore parsing file: {e}", exc_info=True)
        return None, str(e)


# =============================================================================
# ENDPOINT FILE UPLOAD
# =============================================================================

@catalogs_bp.route('/api/catalogs/file/upload', methods=['POST'])
@login_required
@admin_required('analyst')
def upload_file():
    """
    Importa dati fotometrici da file caricato.

    Permessi:
    - superuser: può sempre importare (anche nuove stelle)
    - admin: può importare nuove stelle solo fino al limite dell'associazione
    - analyst: può aggiungere dati solo a stelle già assegnate a loro

    Form data:
    - file: File CSV/TXT con dati fotometrici (obbligatorio)
    - gaia_id: Gaia DR3 ID per associazione (obbligatorio)
    - time_col: Nome colonna tempo (auto-detect se vuoto)
    - mag_col: Nome colonna magnitudine (auto-detect se vuoto)
    - err_col: Nome colonna errore (auto-detect se vuoto)
    - time_format: Formato tempo - hjd, jd, mjd, bjd, btjd (default: hjd)
    - band: Banda fotometrica (opzionale)
    - catalog_name: Nome catalogo/sorgente (opzionale, default: nome file)
    - ra: Right Ascension in gradi (opzionale)
    - dec: Declination in gradi (opzionale)

    Returns:
        JSON con success, import_id, points_imported
    """
    # Verifica file
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file caricato'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nessun file selezionato'}), 400

    # Verifica gaia_id
    gaia_id = request.form.get('gaia_id')
    if not gaia_id:
        return jsonify({'error': 'gaia_id e obbligatorio'}), 400

    # Verifica permessi
    db_check = get_db_session()
    auto_create_project = False
    try:
        # Verifica se l'utente può aggiungere dati a questa stella
        can_add, add_error, existing_project = can_add_data_to_star(
            db_check, gaia_id, current_user.role, current_user.association_id, current_user.id
        )

        if not can_add:
            # Se non può aggiungere dati a stella esistente, verifica se può creare nuova stella
            can_create, create_error = can_create_new_star(
                db_check, current_user.role, current_user.association_id
            )
            if not can_create:
                return jsonify({
                    'error': add_error or create_error
                }), 403
            # Può creare nuova stella (solo admin/superuser)
            auto_create_project = True
    finally:
        db_check.close()

    # Leggi contenuto file
    try:
        file_content = file.read().decode('utf-8')
    except UnicodeDecodeError:
        try:
            file.seek(0)
            file_content = file.read().decode('latin-1')
        except Exception:
            return jsonify({'error': 'Impossibile decodificare il file. Usare encoding UTF-8'}), 400

    if not file_content.strip():
        return jsonify({'error': 'File vuoto'}), 400

    # Parametri opzionali
    time_col = request.form.get('time_col') or None
    mag_col = request.form.get('mag_col') or None
    err_col = request.form.get('err_col') or None
    time_format = request.form.get('time_format', 'hjd')
    band = request.form.get('band') or None
    catalog_name = request.form.get('catalog_name') or file.filename or 'FILE'

    # Coordinate opzionali
    ra = None
    dec = None
    try:
        if request.form.get('ra'):
            ra = float(request.form.get('ra'))
        if request.form.get('dec'):
            dec = float(request.form.get('dec'))
    except (ValueError, TypeError):
        pass

    db = get_db_session()
    try:
        logger.info(f"File upload: {file.filename}, gaia_id={gaia_id}")

        # Step 1: Parse file
        df, parse_error = _parse_file_content(
            content=file_content,
            time_col=time_col,
            mag_col=mag_col,
            err_col=err_col,
            time_format=time_format
        )

        if df is None:
            return jsonify({
                'success': False,
                'error': parse_error or "Errore parsing file"
            }), 400

        # Step 2: Crea record import
        import_record = create_import_record(
            db=db,
            catalog_name=catalog_name,
            search_type='file',
            search_value=catalog_name,
            ra=ra,
            dec=dec,
            radius_arcsec=0,
            gaia_id=gaia_id,
            user_id=current_user.id,
            state='importing'
        )

        # Step 3: Inserisci dati
        points_imported = insert_catalog_data(
            db, gaia_id, catalog_name, df,
            catalog_import_id=import_record.id
        )

        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({
                'success': False,
                'error': "Nessun punto valido importato",
                'import_id': import_record.id
            }), 400

        # Step 4: Calcola statistiche
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name=catalog_name,
            success=True,
            point_count=points_imported,
            band=band or 'unknown',
            time_range=time_range,
            mag_range=mag_range
        )

        # Step 5: Finalizza
        # auto_create_project è già stato determinato nella verifica permessi
        # Per admin: crea progetto se è una nuova stella
        # Per superuser: nessun progetto automatico (bacino centrale)
        # Per analyst: mai crea progetto (può solo aggiungere dati)
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
            catalog_name=catalog_name
        )

        if not success:
            return jsonify({'error': error}), 400

        response = {
            'success': True,
            'import_id': import_record.id,
            'points_imported': points_imported,
            'source_name': catalog_name,
            'gaia_id': gaia_id,
            'time_range': {
                'min': time_range[0],
                'max': time_range[1],
                'span_days': time_range[1] - time_range[0]
            },
            'mag_range': {
                'min': mag_range[0],
                'max': mag_range[1]
            },
            'message': f'Importati {points_imported} punti da {catalog_name}'
        }

        if created_project:
            response['project_created'] = True
            response['project_id'] = created_project.id
            response['project_code'] = created_project.project_code
            response['message'] += f' - Creato progetto {created_project.project_code}'

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"File upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@catalogs_bp.route('/api/catalogs/file/preview', methods=['POST'])
@login_required
@admin_required('analyst')
def preview_file():
    """
    Preview di un file senza importarlo.

    Utile per verificare che il parsing sia corretto prima dell'import.

    Form data:
    - file: File CSV/TXT (obbligatorio)
    - time_col: Nome colonna tempo (auto-detect se vuoto)
    - mag_col: Nome colonna magnitudine (auto-detect se vuoto)
    - err_col: Nome colonna errore (auto-detect se vuoto)
    - time_format: Formato tempo (default: hjd)

    Returns:
        JSON con columns_detected, point_count, preview_data
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file caricato'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nessun file selezionato'}), 400

    # Leggi contenuto
    try:
        file_content = file.read().decode('utf-8')
    except UnicodeDecodeError:
        try:
            file.seek(0)
            file_content = file.read().decode('latin-1')
        except Exception:
            return jsonify({'error': 'Impossibile decodificare il file'}), 400

    if not file_content.strip():
        return jsonify({'error': 'File vuoto'}), 400

    # Parametri
    time_col = request.form.get('time_col') or None
    mag_col = request.form.get('mag_col') or None
    err_col = request.form.get('err_col') or None
    time_format = request.form.get('time_format', 'hjd')

    # Prima passa: leggi raw per mostrare colonne originali
    try:
        lines = [l for l in file_content.split('\n') if l.strip() and not l.strip().startswith('#')]
        delimiter = _detect_delimiter(lines[0] if lines else "")
        raw_df = pd.read_csv(io.StringIO('\n'.join(lines)), delimiter=delimiter, nrows=5)
        original_columns = list(raw_df.columns)
    except Exception:
        original_columns = []

    # Seconda passa: parsing completo
    df, parse_error = _parse_file_content(
        content=file_content,
        time_col=time_col,
        mag_col=mag_col,
        err_col=err_col,
        time_format=time_format
    )

    if df is None:
        return jsonify({
            'success': False,
            'error': parse_error,
            'original_columns': original_columns,
            'suggested_time_col': _find_column(original_columns, TIME_COLUMN_ALIASES),
            'suggested_mag_col': _find_column(original_columns, MAG_COLUMN_ALIASES),
            'suggested_err_col': _find_column(original_columns, ERR_COLUMN_ALIASES)
        }), 400

    # Statistiche
    time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
    mag_range = (float(df['mag'].min()), float(df['mag'].max()))

    return jsonify({
        'success': True,
        'filename': file.filename,
        'original_columns': original_columns,
        'detected_columns': {
            'time': time_col or _find_column(original_columns, TIME_COLUMN_ALIASES),
            'mag': mag_col or _find_column(original_columns, MAG_COLUMN_ALIASES),
            'err': err_col or _find_column(original_columns, ERR_COLUMN_ALIASES)
        },
        'point_count': len(df),
        'time_range': {
            'min': time_range[0],
            'max': time_range[1],
            'span_days': time_range[1] - time_range[0]
        },
        'mag_range': {
            'min': mag_range[0],
            'max': mag_range[1]
        },
        'preview': df.head(20).to_dict(orient='records')
    })


@catalogs_bp.route('/api/catalogs/file/info')
@login_required
@admin_required('analyst')
def file_upload_info():
    """
    Informazioni sui formati file supportati.

    Returns:
        JSON con formati supportati e colonne riconosciute
    """
    return jsonify({
        'supported_formats': ['CSV', 'TSV', 'TXT con spazi'],
        'supported_encodings': ['UTF-8', 'Latin-1'],
        'time_formats': {
            'hjd': 'Heliocentric Julian Date (usato come-e)',
            'jd': 'Julian Date (usato come-e)',
            'mjd': 'Modified Julian Date (+2400000.5)',
            'bjd': 'Barycentric Julian Date (usato come-e)',
            'btjd': 'TESS Barycentric JD (+2457000)'
        },
        'recognized_time_columns': TIME_COLUMN_ALIASES,
        'recognized_mag_columns': MAG_COLUMN_ALIASES,
        'recognized_err_columns': ERR_COLUMN_ALIASES,
        'example_csv': '''# Esempio file CSV
hjd,mag,mag_err
2459000.5,12.34,0.02
2459001.5,12.38,0.03
2459002.5,12.31,0.02''',
        'notes': [
            'Le righe che iniziano con # o // sono ignorate',
            'I nomi colonna sono case-insensitive',
            'Il delimitatore e auto-detected (virgola, tab, spazio)'
        ]
    })
