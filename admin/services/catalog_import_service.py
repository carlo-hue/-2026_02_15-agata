# agata/admin/services/catalog_import_service.py
"""
Catalog Import Service

Orchestrazione ricerche e import da cataloghi fotometrici esterni.
Gestisce:
- Ricerca parallela su multipli cataloghi (TESS, ZTF, ASAS-SN, OGLE)
- Preview risultati disponibili
- Import selettivo in database locale (Cataloghi_esterni)
- Creazione Project AGATA da import completato

AGATA e' autoritativo: i dati vengono importati e gestiti qui.
"""
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from agata.db import SessionLocal
from agata.auth_models import Project, User, Association
from agata.auth_models.catalog_import import CatalogImport
from agata.admin.services.audit_service import log_audit
from agata.admin.services.slack_service import get_slack_service
from agata.services.external_catalogs import (
    TESSClient, ZTFClient, ASASSNClient, OGLEClient, FileClient,
    SearchQuery, CatalogSearchResult
)
from agata.services.external_catalogs.gaia_resolver import resolve_gaia_id

logger = logging.getLogger(__name__)

# Registry cataloghi disponibili
CATALOG_CLIENTS = {
    'TESS': TESSClient,
    'ZTF': ZTFClient,
    'ASAS-SN': ASASSNClient,
    'OGLE': OGLEClient,
}

# Cataloghi abilitati di default (ZTF e ASAS-SN hanno API instabili)
DEFAULT_CATALOGS = ['TESS', 'OGLE']


def get_available_catalogs() -> List[str]:
    """Restituisce lista cataloghi disponibili."""
    return list(CATALOG_CLIENTS.keys())


def search_external_catalogs(
    ra: float,
    dec: float,
    radius_arcsec: float = 5.0,
    gaia_id: Optional[str] = None,
    catalogs: Optional[List[str]] = None,
    user_id: str = None,
    user_email: Optional[str] = None
) -> Tuple[CatalogImport, Dict[str, CatalogSearchResult]]:
    """
    Ricerca parallela su cataloghi esterni.

    Crea un record CatalogImport per tracciare la sessione,
    poi interroga i cataloghi richiesti in parallelo.

    Args:
        ra: Right Ascension in gradi (0-360)
        dec: Declination in gradi (-90 to +90)
        radius_arcsec: Raggio ricerca in arcsec (default 5.0)
        gaia_id: Gaia DR3 ID (opzionale)
        catalogs: Lista cataloghi da interrogare (default: tutti)
        user_id: ID utente richiedente
        user_email: Email utente per audit

    Returns:
        Tuple (CatalogImport record, Dict risultati per catalogo)

    Raises:
        ValueError: Se coordinate non valide
    """
    # Validazione
    if not (0 <= ra <= 360):
        raise ValueError(f"RA deve essere tra 0 e 360, ricevuto: {ra}")
    if not (-90 <= dec <= 90):
        raise ValueError(f"Dec deve essere tra -90 e +90, ricevuto: {dec}")

    db: Session = SessionLocal()

    try:
        # Se non abbiamo un Gaia ID, proviamo a risolverlo dalle coordinate
        resolved_gaia_id = gaia_id
        if not resolved_gaia_id:
            logger.info(f"Tentativo risoluzione Gaia ID per RA={ra}, Dec={dec}")
            gaia_info = resolve_gaia_id(ra, dec, radius_arcsec=max(radius_arcsec, 10.0))
            if gaia_info:
                resolved_gaia_id = gaia_info['source_id']
                logger.info(f"Gaia ID risolto: {resolved_gaia_id} (G={gaia_info.get('phot_g_mean_mag', 'N/A')})")

        # Crea record tracking
        search_value = gaia_id if gaia_id else f"{ra:.6f},{dec:.6f}"
        search_type = 'gaia_id' if gaia_id else 'coordinates'

        import_record = CatalogImport(
            search_type=search_type,
            search_value=search_value,
            search_radius_arcsec=radius_arcsec,
            resolved_ra=ra,
            resolved_dec=dec,
            resolved_gaia_id=resolved_gaia_id,
            state='searching',
            requested_by=user_id
        )
        db.add(import_record)
        db.commit()
        db.refresh(import_record)

        logger.info(f"CatalogImport {import_record.id}: avvio ricerca RA={ra}, Dec={dec}, Gaia={resolved_gaia_id}")

        # Prepara query
        query = SearchQuery(ra=ra, dec=dec, radius_arcsec=radius_arcsec, gaia_id=gaia_id)

        # Determina cataloghi da interrogare
        target_catalogs = catalogs or DEFAULT_CATALOGS
        target_catalogs = [c for c in target_catalogs if c in CATALOG_CLIENTS]

        # Ricerca parallela
        results: Dict[str, CatalogSearchResult] = {}
        catalogs_status = {}
        total_points = 0

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_search_single_catalog, name, query): name
                for name in target_catalogs
            }

            for future in as_completed(futures, timeout=600):
                catalog_name = futures[future]
                try:
                    result = future.result(timeout=180)  # Timeout per singolo catalogo
                    results[catalog_name] = result

                    catalogs_status[catalog_name] = {
                        'status': 'success' if result.success else 'error',
                        'count': result.point_count,
                        'error': result.error_message,
                        'band': result.band,
                        'time_range': result.time_range,
                        'mag_range': result.mag_range,
                        'source_id': result.source_id,
                    }

                    if result.success:
                        total_points += result.point_count

                    logger.info(f"CatalogImport {import_record.id}: {catalog_name} -> {result.point_count} punti")

                except Exception as e:
                    logger.error(f"CatalogImport {import_record.id}: errore {catalog_name}: {e}")
                    catalogs_status[catalog_name] = {
                        'status': 'error',
                        'count': 0,
                        'error': str(e)
                    }

        # Aggiorna record
        import_record.catalogs_queried = catalogs_status
        import_record.total_points_available = total_points
        import_record.state = 'preview'
        db.commit()

        # Audit log
        log_audit(
            user_id=user_id,
            user_email=user_email,
            association_id=None,
            action='catalog_search_completed',
            entity_type='catalog_import',
            entity_id=str(import_record.id),
            new_value=f"{total_points} punti da {list(catalogs_status.keys())}",
            description=f"Ricerca cataloghi esterni: {search_value}"
        )

        return import_record, results

    except Exception as e:
        db.rollback()
        logger.error(f"Errore search_external_catalogs: {e}", exc_info=True)
        raise
    finally:
        db.close()


def _search_single_catalog(catalog_name: str, query: SearchQuery) -> CatalogSearchResult:
    """
    Helper per ricerca su singolo catalogo.

    Args:
        catalog_name: Nome catalogo
        query: SearchQuery

    Returns:
        CatalogSearchResult
    """
    client_class = CATALOG_CLIENTS.get(catalog_name)
    if not client_class:
        return CatalogSearchResult(
            catalog_name=catalog_name,
            success=False,
            error_message=f"Catalogo {catalog_name} non supportato"
        )

    client = client_class()
    return client.search(query)


def import_selected_data(
    import_id: int,
    selected_catalogs: List[str],
    gaia_id: str,
    user_id: str,
    user_email: Optional[str] = None,
    association_id: Optional[int] = None,
    auto_create_project: bool = False,
    association_id_owner: Optional[int] = None
) -> Tuple[bool, Optional[str], int, Optional[Project]]:
    """
    Importa dati selezionati in Cataloghi_esterni.

    Ri-esegue la ricerca sui cataloghi selezionati e inserisce
    i dati nella tabella esistente Cataloghi_esterni.

    Args:
        import_id: ID CatalogImport
        selected_catalogs: Lista cataloghi da importare
        gaia_id: Gaia ID per la colonna Source
        user_id: Utente che importa
        user_email: Email per audit
        association_id: ID associazione per creazione automatica progetto
        auto_create_project: Se True, crea automaticamente un Project 'available'
        association_id_owner: ID associazione proprietaria dei dati (NULL per dati centrali superuser)

    Returns:
        Tuple (success, error_message, points_imported, Project)
        Project è None se auto_create_project=False
    """
    db: Session = SessionLocal()

    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return False, "Import record non trovato", 0, None

        if import_record.state not in ('preview', 'failed'):
            return False, f"Import non in stato preview (stato: {import_record.state})", 0, None

        import_record.state = 'importing'
        import_record.selected_catalogs = selected_catalogs
        db.commit()

        logger.info(f"CatalogImport {import_id}: avvio import per {selected_catalogs}")

        # Ri-esegui ricerca per dati freschi
        query = SearchQuery(
            ra=import_record.resolved_ra,
            dec=import_record.resolved_dec,
            radius_arcsec=import_record.search_radius_arcsec or 5.0,
            gaia_id=gaia_id
        )

        total_imported = 0

        for catalog_name in selected_catalogs:
            if catalog_name not in CATALOG_CLIENTS:
                logger.warning(f"CatalogImport {import_id}: catalogo {catalog_name} non supportato")
                continue

            result = _search_single_catalog(catalog_name, query)

            if result.success and result.data is not None and not result.data.empty:
                points = _insert_catalog_data(
                    db=db,
                    gaia_id=gaia_id,
                    catalog_name=catalog_name,
                    data=result.data,
                    association_id_owner=association_id_owner
                )
                total_imported += points
                logger.info(f"CatalogImport {import_id}: {catalog_name} -> {points} punti importati")

        # Aggiorna record
        import_record.total_points_imported = total_imported
        import_record.resolved_gaia_id = gaia_id
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
            entity_id=str(import_id),
            new_value=f"{total_imported} punti da {selected_catalogs}",
            description=f"Importati {total_imported} punti fotometrici per Gaia ID {gaia_id}"
        )

        # Creazione automatica progetto se richiesto
        created_project = None
        if auto_create_project and association_id:
            # Verifica che non esista già un progetto per questa stella in questa associazione
            existing_project = db.query(Project).filter(
                Project.gaia_id == gaia_id,
                Project.association_id == association_id,
                Project.state != 'cancelled'
            ).first()

            if not existing_project:
                # Verifica associazione
                association = db.query(Association).filter(Association.id == association_id).first()
                if association and association.is_active:
                    # Genera project code
                    project_code = _generate_project_code(db)

                    # Determina source dai cataloghi importati
                    source = ', '.join(selected_catalogs) if selected_catalogs else 'esterni'

                    # Crea il progetto
                    created_project = Project(
                        project_code=project_code,
                        gaia_id=gaia_id,
                        association_id=association_id,
                        title=f"Import cataloghi: {source}",
                        source=source,
                        ra=import_record.resolved_ra,
                        dec_deg=import_record.resolved_dec,
                        state='available'
                    )
                    db.add(created_project)
                    db.flush()

                    # Link import a project
                    import_record.project_id = created_project.id
                    import_record.target_association_id = association_id

                    db.commit()
                    db.refresh(created_project)

                    logger.info(f"CatalogImport {import_id}: creato automaticamente Project {project_code}")

                    # Audit log per creazione progetto
                    log_audit(
                        user_id=user_id,
                        user_email=user_email,
                        association_id=association_id,
                        action='project_created_from_catalog_import',
                        entity_type='project',
                        entity_id=str(created_project.id),
                        new_value=project_code,
                        description=f"Project {project_code} creato automaticamente da import cataloghi"
                    )

                    # Notifica Slack
                    try:
                        slack_service = get_slack_service()
                        slack_service.notify_new_project(db, created_project, association)
                    except Exception as slack_error:
                        logger.warning(f"Notifica Slack fallita per progetto {project_code}: {slack_error}")

        return True, None, total_imported, created_project

    except Exception as e:
        db.rollback()

        # Marca come failed
        try:
            import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
            if import_record:
                import_record.state = 'failed'
                import_record.error_message = str(e)
                db.commit()
        except Exception:
            pass

        logger.error(f"Errore import_selected_data: {e}", exc_info=True)
        return False, str(e), 0, None
    finally:
        db.close()


def _insert_catalog_data(
    db: Session,
    gaia_id: str,
    catalog_name: str,
    data: 'pd.DataFrame',
    association_id_owner: Optional[int] = None
) -> int:
    """
    Inserisce dati fotometrici in Cataloghi_esterni.

    La tabella esistente ha struttura:
    - hjd: Heliocentric Julian Date
    - Vmag: Magnitudine (V-band o equivalente)
    - Source: Gaia ID (bigint)
    - catalogo: Nome catalogo sorgente
    - association_id_owner: ID associazione proprietaria (NULL per dati centrali superuser)

    Args:
        db: Sessione database
        gaia_id: Gaia DR3 source ID (stringa numerica)
        catalog_name: Nome catalogo (es. 'ZTF', 'TESS')
        data: DataFrame con colonne [hjd, mag]
        association_id_owner: Associazione proprietaria dei dati (NULL per dati centrali)

    Returns:
        Numero di righe inserite
    """
    if data is None or data.empty:
        return 0

    # Converti gaia_id in intero (la colonna Source è bigint)
    try:
        # Rimuovi eventuali prefissi/suffissi non numerici
        gaia_id_clean = ''.join(filter(str.isdigit, str(gaia_id)))
        source_id = int(gaia_id_clean) if gaia_id_clean else None
    except (ValueError, TypeError):
        logger.warning(f"Gaia ID non valido per conversione: {gaia_id}")
        source_id = None

    if source_id is None:
        logger.error(f"Impossibile convertire Gaia ID '{gaia_id}' in numero")
        return 0

    # Prepara batch insert
    rows = []
    for _, row in data.iterrows():
        try:
            hjd = float(row['hjd'])
            mag = float(row['mag'])
            if not (hjd > 0 and -30 < mag < 30):  # Sanity check
                continue
            rows.append({
                'hjd': hjd,
                'vmag': mag,
                'source': source_id,
                'catalogo': catalog_name,
                'association_id_owner': association_id_owner
            })
        except (ValueError, TypeError):
            continue

    if not rows:
        return 0

    # Batch insert
    insert_sql = text("""
        INSERT INTO Cataloghi_esterni (hjd, Vmag, Source, catalogo, association_id_owner)
        VALUES (:hjd, :vmag, :source, :catalogo, :association_id_owner)
    """)

    db.execute(insert_sql, rows)
    db.commit()

    return len(rows)


def create_project_from_import(
    import_id: int,
    association_id: int,
    user_id: str,
    user_email: Optional[str] = None,
    title: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Crea Project AGATA da importazione completata.

    Il Project viene creato in stato 'available' e assegnato
    all'associazione specificata. Il referente dell'associazione
    potra' poi assegnarlo ad un analyst.

    Args:
        import_id: ID CatalogImport
        association_id: ID associazione target
        user_id: Superuser che crea
        user_email: Email per audit
        title: Titolo progetto (opzionale)

    Returns:
        Tuple (success, error, Project)
    """
    db: Session = SessionLocal()

    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return False, "Import record non trovato", None

        if import_record.state != 'completed':
            return False, f"Import non completato (stato: {import_record.state})", None

        if import_record.project_id is not None:
            existing = db.query(Project).filter(Project.id == import_record.project_id).first()
            if existing:
                return False, f"Project gia' creato: {existing.project_code}", None

        # Verifica associazione
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return False, f"Associazione {association_id} non trovata", None

        if not association.is_active:
            return False, f"Associazione {association.name} non attiva", None

        gaia_id = import_record.resolved_gaia_id or import_record.search_value

        # Verifica duplicati (solo progetti attivi, non cancellati, STESSA ASSOCIAZIONE)
        # Una stella può avere progetti attivi in associazioni diverse
        existing = db.query(Project).filter(
            Project.gaia_id == gaia_id,
            Project.association_id == association_id,
            Project.state != 'cancelled'
        ).first()
        if existing:
            return False, f"Project attivo con Gaia ID {gaia_id} esiste gia' in questa associazione ({existing.project_code})", None

        # Genera project code
        project_code = _generate_project_code(db)

        # Determina source dai cataloghi importati
        source = None
        if import_record.selected_catalogs:
            source = ', '.join(import_record.selected_catalogs)

        # Crea project
        project = Project(
            project_code=project_code,
            gaia_id=gaia_id,
            association_id=association_id,
            title=title or f"Import cataloghi: {source or 'esterni'}",
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

        logger.info(f"CatalogImport {import_id}: creato Project {project_code} per associazione {association.name}")

        # Audit log
        log_audit(
            user_id=user_id,
            user_email=user_email,
            association_id=association_id,
            action='project_created_from_import',
            entity_type='project',
            entity_id=str(project.id),
            new_value=project_code,
            description=f"Project {project_code} creato da import cataloghi (import_id={import_id})"
        )

        # Notifica Slack (best-effort, non blocca il successo)
        try:
            slack_service = get_slack_service()
            slack_service.notify_new_project(db, project, association)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack fallita per progetto {project_code}: {slack_error}")

        return True, None, project

    except Exception as e:
        db.rollback()
        logger.error(f"Errore create_project_from_import: {e}", exc_info=True)
        return False, str(e), None
    finally:
        db.close()


def _generate_project_code(db: Session) -> str:
    """
    Genera codice progetto univoco.

    Formato: AGATA-YYYY-NNN (es: AGATA-2026-001)
    """
    year = datetime.now().year

    # Trova ultimo codice dell'anno
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


def get_import_by_id(import_id: int) -> Optional[CatalogImport]:
    """
    Recupera CatalogImport per ID.

    Args:
        import_id: ID record

    Returns:
        CatalogImport o None
    """
    db: Session = SessionLocal()
    try:
        return db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
    finally:
        db.close()


def list_imports(
    user_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50
) -> List[CatalogImport]:
    """
    Lista importazioni con filtri.

    Args:
        user_id: Filtra per utente (None = tutti, per superuser)
        state: Filtra per stato
        limit: Numero max risultati

    Returns:
        Lista CatalogImport
    """
    db: Session = SessionLocal()
    try:
        query = db.query(CatalogImport)

        if user_id:
            query = query.filter(CatalogImport.requested_by == user_id)

        if state:
            query = query.filter(CatalogImport.state == state)

        return query.order_by(CatalogImport.created_at.desc()).limit(limit).all()
    finally:
        db.close()


def cancel_import(import_id: int, user_id: str, reason: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Cancella un import in corso o in preview.

    Args:
        import_id: ID CatalogImport
        user_id: Utente che cancella
        reason: Motivazione

    Returns:
        Tuple (success, error_message)
    """
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return False, "Import non trovato"

        if import_record.state in ('completed', 'cancelled'):
            return False, f"Import non cancellabile (stato: {import_record.state})"

        import_record.state = 'cancelled'
        import_record.error_message = reason or "Cancellato dall'utente"
        db.commit()

        logger.info(f"CatalogImport {import_id}: cancellato da {user_id}")

        return True, None

    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def import_from_file(
    file_content: str,
    gaia_id: str,
    user_id: str,
    user_email: Optional[str] = None,
    time_col: Optional[str] = None,
    mag_col: Optional[str] = None,
    err_col: Optional[str] = None,
    time_format: str = 'hjd',
    band: Optional[str] = None,
    source_name: Optional[str] = None,
    ra: Optional[float] = None,
    dec: Optional[float] = None,
    association_id: Optional[int] = None,
    auto_create_project: bool = False
) -> Tuple[bool, Optional[str], int, Optional[CatalogImport], Optional[Project]]:
    """
    Importa dati fotometrici da contenuto file.

    Args:
        file_content: Contenuto del file (CSV/TXT)
        gaia_id: Gaia DR3 ID per associazione
        user_id: ID utente che importa
        user_email: Email per audit
        time_col: Nome colonna tempo (auto-detect se None)
        mag_col: Nome colonna magnitudine (auto-detect se None)
        err_col: Nome colonna errore (auto-detect se None)
        time_format: Formato tempo ('hjd', 'jd', 'mjd', 'bjd', 'btjd')
        band: Banda fotometrica
        source_name: Nome file/sorgente
        ra: Right Ascension (opzionale, per metadata)
        dec: Declination (opzionale, per metadata)
        association_id: ID associazione per creazione automatica progetto
        auto_create_project: Se True, crea automaticamente un Project 'available'

    Returns:
        Tuple (success, error_message, points_imported, CatalogImport, Project)
        Project è None se auto_create_project=False o se superuser (bacino centrale)
    """
    db: Session = SessionLocal()

    try:
        # Crea record tracking
        import_record = CatalogImport(
            search_type='file',
            search_value=source_name or 'file',
            search_radius_arcsec=0,
            resolved_ra=ra,
            resolved_dec=dec,
            resolved_gaia_id=gaia_id,
            state='importing',
            requested_by=user_id
        )
        db.add(import_record)
        db.commit()
        db.refresh(import_record)

        logger.info(f"CatalogImport {import_record.id}: import da file '{source_name}'")

        # Parse file con FileClient
        client = FileClient()
        result = client.load_from_string(
            content=file_content,
            time_col=time_col,
            mag_col=mag_col,
            err_col=err_col,
            time_format=time_format,
            band=band,
            source_name=source_name
        )

        if not result.success:
            import_record.state = 'failed'
            import_record.error_message = result.error_message
            db.commit()
            return False, result.error_message, 0, import_record

        if result.data is None or result.data.empty:
            import_record.state = 'failed'
            import_record.error_message = "Nessun dato valido nel file"
            db.commit()
            return False, "Nessun dato valido nel file", 0, import_record

        # Inserisci in database
        # Usa il nome sorgente come nome catalogo
        catalog_name = source_name or 'FILE'

        points = _insert_catalog_data(
            db=db,
            gaia_id=gaia_id,
            catalog_name=catalog_name,
            data=result.data
        )

        # Aggiorna record
        import_record.total_points_available = result.point_count
        import_record.total_points_imported = points
        import_record.selected_catalogs = [catalog_name]
        import_record.catalogs_queried = {
            catalog_name: {
                'status': 'success',
                'count': points,
                'band': band or result.band,
                'time_range': result.time_range,
                'mag_range': result.mag_range
            }
        }
        import_record.state = 'completed'
        import_record.completed_at = datetime.utcnow()
        db.commit()

        logger.info(f"CatalogImport {import_record.id}: importati {points} punti da file")

        # Audit log
        log_audit(
            user_id=user_id,
            user_email=user_email,
            association_id=association_id,
            action='catalog_import_from_file',
            entity_type='catalog_import',
            entity_id=str(import_record.id),
            new_value=f"{points} punti da file '{source_name}'",
            description=f"Importati {points} punti fotometrici da file per Gaia ID {gaia_id}"
        )

        # Creazione automatica progetto se richiesto
        created_project = None
        if auto_create_project and association_id:
            # Verifica che non esista già un progetto per questa stella in questa associazione
            existing_project = db.query(Project).filter(
                Project.gaia_id == gaia_id,
                Project.association_id == association_id,
                Project.state != 'cancelled'
            ).first()

            if not existing_project:
                # Verifica associazione
                association = db.query(Association).filter(Association.id == association_id).first()
                if association and association.is_active:
                    # Genera project code
                    project_code = _generate_project_code(db)

                    # Crea il progetto
                    created_project = Project(
                        project_code=project_code,
                        gaia_id=gaia_id,
                        association_id=association_id,
                        title=f"Import file: {source_name or 'dati'}",
                        source=source_name or 'FILE',
                        ra=ra,
                        dec_deg=dec,
                        state='available'
                    )
                    db.add(created_project)
                    db.flush()

                    # Link import a project
                    import_record.project_id = created_project.id
                    import_record.target_association_id = association_id

                    db.commit()
                    db.refresh(created_project)

                    logger.info(f"CatalogImport {import_record.id}: creato automaticamente Project {project_code}")

                    # Audit log per creazione progetto
                    log_audit(
                        user_id=user_id,
                        user_email=user_email,
                        association_id=association_id,
                        action='project_created_from_file_import',
                        entity_type='project',
                        entity_id=str(created_project.id),
                        new_value=project_code,
                        description=f"Project {project_code} creato automaticamente da import file"
                    )

                    # Notifica Slack
                    try:
                        slack_service = get_slack_service()
                        slack_service.notify_new_project(db, created_project, association)
                    except Exception as slack_error:
                        logger.warning(f"Notifica Slack fallita per progetto {project_code}: {slack_error}")

        return True, None, points, import_record, created_project

    except Exception as e:
        db.rollback()

        # Marca come failed se abbiamo un record
        try:
            if import_record:
                import_record.state = 'failed'
                import_record.error_message = str(e)
                db.commit()
        except Exception:
            pass

        logger.error(f"Errore import_from_file: {e}", exc_info=True)
        return False, str(e), 0, None, None
    finally:
        db.close()
