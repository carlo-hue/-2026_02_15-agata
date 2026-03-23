# agata/admin/routes/catalogs/common.py
"""
Funzioni comuni condivise da tutti gli endpoint cataloghi.

Queste funzioni NON cambiano tra cataloghi:
- Gestione record CatalogImport
- Inserimento dati in Cataloghi_esterni
- Risoluzione Gaia ID
- Normalizzazione tempi
- Creazione Project
"""
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import logging
import requests
import pandas as pd

from sqlalchemy.orm import Session
from sqlalchemy import text

from agata.db import SessionLocal
from agata.auth_models import Project, Association
from agata.auth_models.catalog_import import CatalogImport
from agata.admin.services.audit_service import log_audit
from agata.admin.services.slack_service import get_slack_service

logger = logging.getLogger(__name__)


# =============================================================================
# RISOLUZIONE GAIA ID
# =============================================================================

GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"

def resolve_gaia_id(ra: float, dec: float, radius_arcsec: float = 10.0) -> Optional[Dict[str, Any]]:
    """
    Risolve Gaia DR3 source_id dalle coordinate via TAP query.

    Cerca la sorgente piu' luminosa nel raggio specificato.

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        radius_arcsec: Raggio ricerca in arcsec

    Returns:
        Dict con {source_id, ra, dec, phot_g_mean_mag} o None
    """
    radius_deg = radius_arcsec / 3600.0

    query = f"""
    SELECT TOP 1
        source_id, ra, dec, phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(
        POINT('ICRS', ra, dec),
        CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
    )
    ORDER BY phot_g_mean_mag ASC
    """

    try:
        resp = requests.post(
            GAIA_TAP_URL,
            data={
                'REQUEST': 'doQuery',
                'LANG': 'ADQL',
                'FORMAT': 'json',
                'QUERY': query
            },
            timeout=30
        )
        resp.raise_for_status()

        data = resp.json()
        if 'data' in data and data['data']:
            row = data['data'][0]
            return {
                'source_id': str(row[0]),
                'ra': row[1],
                'dec': row[2],
                'phot_g_mean_mag': row[3]
            }
        return None

    except Exception as e:
        logger.warning(f"Gaia resolve failed: {e}")
        return None

# =============================================================================
# GAIA ID coordinate
# =============================================================================

def resolve_gaia_coordinates(source_id: str, full_params: bool = False) -> Optional[Dict[str, Any]]:
    """
    Risolve coordinate RA/Dec + parametri stellari da Gaia DR3 source_id.
    Se non trovato in DR3, fallback a DR2 (per stelle rimpiazzate o non aggiornate).

    Args:
        source_id: Gaia DR3 source_id (o DR2 se stella rimossa da DR3)
        full_params: Se True, recupera anche logg, mh, radius, luminosity, distance
                     (utile per analisi di supporto AAVSO/VSX)

    Returns:
        Dict con parametri stella o None

        Modalità standard:
        {source_id, ra, dec, phot_g_mean_mag, bp_rp, teff}

        Modalità full_params=True:
        {source_id, ra, dec, phot_g_mean_mag, bp_rp, teff, logg, mh,
         radius, luminosity, distance, parallax, pmra, pmdec}
    """
    # Estrai source_id numerico da "Gaia DR3 XXXXXXXXX" se necessario
    numeric_source_id = source_id.replace("Gaia DR3 ", "").strip()

    # STEP 1: Prova DR3 (catalogo principale)
    logger.info(f"Attempting Gaia DR3 query for source_id {numeric_source_id}")
    result = _query_gaia_tap(numeric_source_id, "gaiadr3.gaia_source", full_params)
    if result:
        logger.info(f"✅ Found in Gaia DR3: {numeric_source_id}")
        return result

    # STEP 2: Fallback a DR2 se non trovato in DR3
    # (alcune stelle sono state rimpiazzate o non aggiornate in DR3)
    logger.warning(f"Not found in Gaia DR3, attempting DR2 fallback for {numeric_source_id}")
    result = _query_gaia_tap(numeric_source_id, "gaiadr2.gaia_source", full_params=False)
    if result:
        logger.info(f"⚠️  Found in Gaia DR2 (fallback): {numeric_source_id}")
        return result

    logger.warning(f"Source {numeric_source_id} not found in DR3 or DR2")
    return None


def _query_gaia_tap(numeric_source_id: str, table: str, full_params: bool = False) -> Optional[Dict[str, Any]]:
    """
    Query helper per TAP Gaia (DR2 o DR3).

    Args:
        numeric_source_id: Source ID numerico
        table: Nome tabella ("gaiadr3.gaia_source" o "gaiadr2.gaia_source")
        full_params: Se True, recupera parametri estesi (solo per DR3)

    Returns:
        Dict con dati stella o None
    """
    is_dr3 = "gaiadr3" in table

    if is_dr3 and full_params:
        # Query estesa DR3 con GSP-Phot
        query = (
            f"SELECT gs.source_id, gs.ra, gs.dec, gs.parallax, gs.pmra, gs.pmdec, "
            f"gs.phot_g_mean_mag, gs.bp_rp, gs.teff_gspphot, gs.logg_gspphot, "
            f"gs.mh_gspphot, gs.distance_gspphot "
            f"FROM {table} AS gs WHERE gs.source_id = {numeric_source_id}"
        )
    else:
        # Query standard (DR2 o DR3 senza parametri estesi)
        # DR2 non ha teff_gspphot, usa teff_gaia invece
        teff_col = "teff_gspphot" if is_dr3 else "teff_val"
        query = (
            f"SELECT gs.source_id, gs.ra, gs.dec, gs.phot_g_mean_mag, gs.bp_rp, gs.{teff_col} "
            f"FROM {table} AS gs WHERE gs.source_id = {numeric_source_id}"
        )

    try:
        resp = requests.post(
            GAIA_TAP_URL,
            data={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "json",
                "QUERY": query,
            },
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json()
        if data.get("data") and len(data["data"]) > 0:
            row = data["data"][0]

            if is_dr3 and full_params:
                # DR3 con parametri estesi
                return {
                    "source_id": str(row[0]),
                    "ra": row[1],
                    "dec": row[2],
                    "parallax": row[3],
                    "pmra": row[4],
                    "pmdec": row[5],
                    "phot_g_mean_mag": row[6],
                    "bp_rp": row[7],
                    "teff": row[8],
                    "logg": row[9],
                    "mh": row[10],
                    "distance": row[11],  # pc
                    "radius": None,  # Non disponibile in gaia_source
                    "luminosity": None,  # Non disponibile in gaia_source
                }
            else:
                # Query standard (DR2 o DR3 senza estesi)
                return {
                    "source_id": str(row[0]),
                    "ra": row[1],
                    "dec": row[2],
                    "phot_g_mean_mag": row[3],
                    "bp_rp": row[4] if row[4] is not None else None,
                    "teff": row[5] if row[5] is not None else None,
                }

        return None

    except Exception as e:
        logger.debug(f"TAP query failed for {numeric_source_id} in {table}: {str(e)[:100]}")
        return None

# =============================================================================
# NORMALIZZAZIONE TEMPO
# =============================================================================

def normalize_time(time_values: pd.Series, time_format: str) -> pd.Series:
    """
    Normalizza valori temporali in HJD.

    Args:
        time_values: Serie pandas con valori temporali
        time_format: Formato input ('hjd', 'jd', 'mjd', 'bjd', 'btjd')

    Returns:
        Serie pandas con valori in HJD
    """
    time_format = time_format.lower()

    if time_format in ('hjd', 'jd', 'bjd'):
        return time_values
    elif time_format == 'mjd':
        return time_values + 2400000.5
    elif time_format == 'btjd':
        return time_values + 2457000.0
    else:
        logger.warning(f"Formato tempo sconosciuto: {time_format}, assumo HJD")
        return time_values


# =============================================================================
# GESTIONE CATALOG IMPORT RECORD
# =============================================================================

def create_import_record(
    db: Session,
    catalog_name: str,
    search_type: str,
    search_value: str,
    ra: Optional[float],
    dec: Optional[float],
    radius_arcsec: float,
    gaia_id: Optional[str],
    user_id: str,
    state: str = 'searching'
) -> CatalogImport:
    """
    Crea un nuovo record CatalogImport.

    Args:
        db: Sessione database
        catalog_name: Nome catalogo (TESS, ZTF, etc.)
        search_type: Tipo ricerca (coordinates, gaia_id, file)
        search_value: Valore ricerca
        ra: Right Ascension
        dec: Declination
        radius_arcsec: Raggio ricerca
        gaia_id: Gaia ID se noto
        user_id: ID utente
        state: Stato iniziale

    Returns:
        CatalogImport record
    """
    import_record = CatalogImport(
        search_type=search_type,
        search_value=search_value,
        search_radius_arcsec=radius_arcsec,
        resolved_ra=ra,
        resolved_dec=dec,
        resolved_gaia_id=gaia_id,
        state=state,
        requested_by=user_id,
        selected_catalogs=[catalog_name]
    )
    db.add(import_record)
    db.commit()
    db.refresh(import_record)

    logger.info(f"CatalogImport {import_record.id} creato per {catalog_name}")
    return import_record


def update_import_with_results(
    db: Session,
    import_record: CatalogImport,
    catalog_name: str,
    success: bool,
    point_count: int,
    error_message: Optional[str] = None,
    band: Optional[str] = None,
    source_id: Optional[str] = None,
    time_range: Optional[Tuple[float, float]] = None,
    mag_range: Optional[Tuple[float, float]] = None
) -> None:
    """
    Aggiorna il record CatalogImport con i risultati della ricerca.
    """
    import_record.catalogs_queried = {
        catalog_name: {
            'status': 'success' if success else 'error',
            'count': point_count,
            'error': error_message,
            'band': band,
            'source_id': source_id,
            'time_range': time_range,
            'mag_range': mag_range
        }
    }
    import_record.total_points_available = point_count if success else 0
    import_record.state = 'completed' if success else 'failed'

    if error_message and not success:
        import_record.error_message = error_message

    db.commit()


# =============================================================================
# INSERIMENTO DATI IN DATABASE
# =============================================================================

def insert_catalog_data(
    db: Session,
    gaia_id: str,
    catalog_name: str,
    data: pd.DataFrame,
    association_id_owner: Optional[int] = None,
    catalog_import_id: Optional[int] = None
) -> int:
    """
    Inserisce dati fotometrici in Cataloghi_esterni.

    La tabella ha struttura:
    - hjd: Heliocentric Julian Date
    - Vmag: Magnitudine
    - Source: Gaia ID (bigint)
    - catalogo: Nome catalogo
    - catalog_import_id: ID dell'import (per tracciabilità)
    - association_id_owner: ID associazione proprietaria dei dati (NULL = dati centrali)

    Args:
        db: Sessione database
        gaia_id: Gaia DR3 source ID
        catalog_name: Nome catalogo
        data: DataFrame con colonne [hjd, mag, mag_err (opz.)]
        association_id_owner: Associazione proprietaria dei dati (NULL per dati centrali superuser)
        catalog_import_id: ID del CatalogImport che ha generato questi dati

    Returns:
        Numero di righe inserite
    """
    if data is None or data.empty:
        return 0

    # Converti gaia_id in intero
    try:
        gaia_id_clean = ''.join(filter(str.isdigit, str(gaia_id)))
        source_id = int(gaia_id_clean) if gaia_id_clean else None
    except (ValueError, TypeError):
        logger.warning(f"Gaia ID non valido: {gaia_id}")
        return 0

    if source_id is None:
        logger.error(f"Impossibile convertire Gaia ID '{gaia_id}'")
        return 0

    # Prepara righe per insert
    rows = []
    for _, row in data.iterrows():
        try:
            hjd = float(row['hjd'])
            mag = float(row['mag'])
            # Sanity check
            if not (hjd > 0 and -30 < mag < 30):
                continue
            rows.append({
                'hjd': hjd,
                'vmag': mag,
                'source': source_id,
                'catalogo': catalog_name,
                'catalog_import_id': catalog_import_id,
                'association_id_owner': association_id_owner
            })
        except (ValueError, TypeError, KeyError):
            continue

    if not rows:
        return 0

    # Batch insert
    insert_sql = text("""
        INSERT INTO Cataloghi_esterni (hjd, Vmag, Source, catalogo, catalog_import_id, association_id_owner)
        VALUES (:hjd, :vmag, :source, :catalogo, :catalog_import_id, :association_id_owner)
    """)

    db.execute(insert_sql, rows)
    db.commit()

    owner_desc = f"associazione {association_id_owner}" if association_id_owner else "bacino centrale (superuser)"
    import_desc = f"import {catalog_import_id}" if catalog_import_id else "senza tracciamento"
    logger.info(f"Inseriti {len(rows)} punti per {catalog_name}, Gaia ID {gaia_id}, owner: {owner_desc}, {import_desc}")
    return len(rows)


# =============================================================================
# CREAZIONE PROJECT
# =============================================================================

def generate_project_code(db: Session) -> str:
    """
    Genera codice progetto univoco.

    Formato: AGATA-YYYY-NNN
    """
    year = datetime.now().year

    last_project = db.query(Project).filter(
        Project.project_code.like(f'AGATA-{year}-%')
    ).order_by(Project.project_code.desc()).first()

    if last_project:
        try:
            last_num = int(last_project.project_code.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f'AGATA-{year}-{next_num:03d}'


def create_project_if_needed(
    db: Session,
    import_record: CatalogImport,
    association_id: int,
    user_id: str,
    user_email: Optional[str] = None,
    catalog_name: Optional[str] = None
) -> Optional[Project]:
    """
    Crea un Project se richiesto e non esiste gia'.

    Args:
        db: Sessione database
        import_record: Record CatalogImport
        association_id: ID associazione
        user_id: ID utente
        user_email: Email per audit
        catalog_name: Nome catalogo per titolo

    Returns:
        Project creato o None
    """
    gaia_id = import_record.resolved_gaia_id
    if not gaia_id:
        return None

    # Verifica duplicati
    existing = db.query(Project).filter(
        Project.gaia_id == gaia_id,
        Project.association_id == association_id,
        Project.state != 'cancelled'
    ).first()

    if existing:
        logger.info(f"Project gia' esistente per Gaia ID {gaia_id}: {existing.project_code}")
        return None

    # Verifica associazione
    association = db.query(Association).filter(Association.id == association_id).first()
    if not association or not association.is_active:
        return None

    # Genera codice e crea project
    project_code = generate_project_code(db)
    source = catalog_name or ', '.join(import_record.selected_catalogs or ['esterni'])

    project = Project(
        project_code=project_code,
        gaia_id=gaia_id,
        association_id=association_id,
        title=f"Import catalogo: {source}",
        source=source,
        ra=import_record.resolved_ra,
        dec_deg=import_record.resolved_dec,
        state='available'
    )
    db.add(project)
    db.flush()

    # Link import a project
    import_record.project_id = project.id
    import_record.target_association_id = association_id

    db.commit()
    db.refresh(project)

    logger.info(f"Creato Project {project_code} da import {import_record.id}")

    # Audit log
    log_audit(
        user_id=user_id,
        user_email=user_email,
        association_id=association_id,
        action='project_created_from_catalog_import',
        entity_type='project',
        entity_id=str(project.id),
        new_value=project_code,
        description=f"Project {project_code} creato da import catalogo {source}"
    )

    # Notifica Slack (best-effort)
    try:
        slack_service = get_slack_service()
        slack_service.notify_new_project(db, project, association)
    except Exception as e:
        logger.warning(f"Notifica Slack fallita: {e}")

    return project


# =============================================================================
# FINALIZZAZIONE IMPORT
# =============================================================================

def finalize_import(
    db: Session,
    import_record: CatalogImport,
    points_imported: int,
    user_id: str,
    user_email: Optional[str] = None,
    association_id: Optional[int] = None,
    auto_create_project: bool = False,
    catalog_name: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Finalizza un import: aggiorna record, crea project se richiesto.

    Args:
        db: Sessione database
        import_record: Record CatalogImport
        points_imported: Numero punti importati
        user_id: ID utente
        user_email: Email per audit
        association_id: ID associazione per project
        auto_create_project: Se creare project automaticamente
        catalog_name: Nome catalogo

    Returns:
        Tuple (success, error_message, project)
    """
    try:
        import_record.total_points_imported = points_imported
        import_record.state = 'completed'
        import_record.completed_at = datetime.utcnow()
        db.commit()

        # Audit log
        log_audit(
            user_id=user_id,
            user_email=user_email,
            association_id=association_id,
            action='catalog_import_completed',
            entity_type='catalog_import',
            entity_id=str(import_record.id),
            new_value=f"{points_imported} punti da {catalog_name or 'catalogo'}",
            description=f"Importati {points_imported} punti per Gaia ID {import_record.resolved_gaia_id}"
        )

        # Crea project se richiesto
        created_project = None
        if auto_create_project and association_id:
            created_project = create_project_if_needed(
                db=db,
                import_record=import_record,
                association_id=association_id,
                user_id=user_id,
                user_email=user_email,
                catalog_name=catalog_name
            )

        return True, None, created_project

    except Exception as e:
        db.rollback()
        import_record.state = 'failed'
        import_record.error_message = str(e)
        db.commit()
        logger.error(f"Errore finalize_import: {e}", exc_info=True)
        return False, str(e), None


# =============================================================================
# UTILITA' VARIE
# =============================================================================

def get_db_session() -> Session:
    """Crea una nuova sessione database."""
    return SessionLocal()


def validate_coordinates(ra: Any, dec: Any) -> Tuple[bool, Optional[str], Optional[float], Optional[float]]:
    """
    Valida e converte coordinate RA/Dec.

    Returns:
        Tuple (valid, error_message, ra_float, dec_float)
    """
    try:
        ra_f = float(ra)
        dec_f = float(dec)
    except (ValueError, TypeError):
        return False, "Coordinate non valide", None, None

    if not (0 <= ra_f <= 360):
        return False, "RA deve essere tra 0 e 360", None, None
    if not (-90 <= dec_f <= 90):
        return False, "Dec deve essere tra -90 e +90", None, None

    return True, None, ra_f, dec_f


def get_import_record(db: Session, import_id: int, user_id: str, is_superuser: bool) -> Tuple[Optional[CatalogImport], Optional[str]]:
    """
    Recupera un CatalogImport verificando i permessi.

    Returns:
        Tuple (import_record, error_message)
    """
    import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()

    if not import_record:
        return None, "Import non trovato"

    if not is_superuser and import_record.requested_by != user_id:
        return None, "Non autorizzato"

    return import_record, None


# =============================================================================
# VERIFICA PERMESSI IMPORT
# =============================================================================

DEFAULT_MAX_STARS_PER_ASSOCIATION = 30


def get_association_star_limit(association: Association) -> int:
    """
    Restituisce il limite massimo di stelle per un'associazione.

    Il limite è memorizzato in association.settings['max_stars'].
    Default: 30

    Args:
        association: Associazione da verificare

    Returns:
        Limite massimo stelle
    """
    if association.settings and 'max_stars' in association.settings:
        try:
            return int(association.settings['max_stars'])
        except (ValueError, TypeError):
            pass
    return DEFAULT_MAX_STARS_PER_ASSOCIATION


def count_association_stars(db: Session, association_id: int) -> int:
    """
    Conta il numero di stelle (progetti non cancellati) di un'associazione.

    Args:
        db: Sessione database
        association_id: ID associazione

    Returns:
        Numero di stelle/progetti attivi
    """
    return db.query(Project).filter(
        Project.association_id == association_id,
        Project.state != 'cancelled'
    ).count()


def can_create_new_star(
    db: Session,
    user_role: str,
    association_id: Optional[int]
) -> Tuple[bool, Optional[str]]:
    """
    Verifica se l'utente può creare una nuova stella/progetto.

    Regole:
    - superuser: può sempre creare
    - admin: può creare solo se sotto il limite dell'associazione
    - analyst: NON può creare nuove stelle

    Args:
        db: Sessione database
        user_role: Ruolo utente (superuser, admin, analyst)
        association_id: ID associazione dell'utente

    Returns:
        Tuple (can_create, error_message)
    """
    # Superuser può sempre
    if user_role == 'superuser':
        return True, None

    # Analyst non può mai creare nuove stelle
    if user_role in ('analyst', 'reviewer', 'viewer'):
        return False, "Solo admin e superuser possono importare nuove stelle"

    # Admin: verifica limite associazione
    if user_role == 'admin':
        if not association_id:
            return False, "Admin deve appartenere a un'associazione"

        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return False, "Associazione non trovata"

        if not association.is_active:
            return False, "Associazione non attiva"

        current_count = count_association_stars(db, association_id)
        max_stars = get_association_star_limit(association)

        if current_count >= max_stars:
            return False, f"Limite stelle raggiunto per {association.name}: {current_count}/{max_stars}. Contatta un superuser."

        return True, None

    return False, "Ruolo non autorizzato"


def can_add_data_to_star(
    db: Session,
    gaia_id: str,
    user_role: str,
    association_id: Optional[int],
    user_id: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Verifica se l'utente può aggiungere dati a una stella esistente.

    Workflow:
    - superuser: può sempre aggiungere dati (anche a stelle senza progetto)
    - admin: può aggiungere dati solo a stelle con progetto nella propria associazione
    - analyst: può aggiungere dati solo a stelle ASSEGNATE A LUI (stato assigned/in_review)

    Args:
        db: Sessione database
        gaia_id: Gaia ID della stella
        user_role: Ruolo utente
        association_id: ID associazione dell'utente
        user_id: ID utente (necessario per analyst)

    Returns:
        Tuple (can_add, error_message, existing_project)
    """
    # Superuser può sempre
    if user_role == 'superuser':
        project = db.query(Project).filter(
            Project.gaia_id == gaia_id,
            Project.state != 'cancelled'
        ).first()
        return True, None, project

    # Admin: può aggiungere dati a qualsiasi progetto della sua associazione
    if user_role == 'admin':
        if not association_id:
            return False, "Admin deve appartenere a un'associazione", None

        project = db.query(Project).filter(
            Project.gaia_id == gaia_id,
            Project.association_id == association_id,
            Project.state != 'cancelled'
        ).first()

        if not project:
            return False, f"Nessun progetto per Gaia ID {gaia_id} nella tua associazione", None

        return True, None, project

    # Analyst: può aggiungere dati SOLO a stelle assegnate a lui
    if user_role == 'analyst':
        if not association_id or not user_id:
            return False, "Dati utente incompleti", None

        project = db.query(Project).filter(
            Project.gaia_id == gaia_id,
            Project.association_id == association_id,
            Project.assigned_to == user_id,
            Project.state.in_(['assigned', 'in_review']),
        ).first()

        if not project:
            return False, f"Puoi aggiungere dati solo a stelle assegnate a te. Gaia ID {gaia_id} non trovato tra i tuoi progetti.", None

        return True, None, project

    return False, "Ruolo non autorizzato", None


def star_exists_in_catalog(db: Session, gaia_id: str) -> bool:
    """
    Verifica se esistono dati per una stella nel catalogo esterno.

    Args:
        db: Sessione database
        gaia_id: Gaia ID della stella

    Returns:
        True se esistono dati
    """
    try:
        gaia_id_clean = ''.join(filter(str.isdigit, str(gaia_id)))
        source_id = int(gaia_id_clean) if gaia_id_clean else None

        if not source_id:
            return False

        result = db.execute(
            text("SELECT 1 FROM Cataloghi_esterni WHERE Source = :source LIMIT 1"),
            {'source': source_id}
        ).fetchone()

        return result is not None
    except Exception:
        return False
