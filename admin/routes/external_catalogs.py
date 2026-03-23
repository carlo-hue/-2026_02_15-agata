# agata/admin/routes/external_catalogs.py
"""
External Catalogs Routes

Interfaccia admin per recupero dati fotometrici da cataloghi esterni:
- Ricerca stelle su cataloghi (TESS, ZTF, ASAS-SN, OGLE)
- Preview dati disponibili
- Import selettivo in database locale
- Creazione Project AGATA da import
"""
from flask import render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import Session

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, superuser_required, audit_action
from agata.admin.services.catalog_import_service import (
    search_external_catalogs,
    import_selected_data,
    create_project_from_import,
    get_import_by_id,
    list_imports,
    cancel_import,
    get_available_catalogs,
    import_from_file,
)
from agata.auth_models import Association
from agata.auth_models.catalog_import import CatalogImport
from agata.auth_models.project import Project
from agata.db import SessionLocal


@admin_bp.route('/external-catalogs')
@login_required
@admin_required('analyst')
def external_catalogs_page():
    """
    Pagina principale ricerca cataloghi esterni.

    Mostra form di ricerca e lista importazioni filtrabili, ordinabili e paginabili.
    - Superuser: vede tutto + filtro per associazione
    - Admin: vede le sue importazioni
    - Analyst: vede le sue importazioni e puo' cercare solo per stelle assegnate

    Query parameters:
    - state: filtro per stato (all, preview, completed, failed, cancelled)
    - association_id: filtro per associazione (solo superuser)
    - date_filter: filtro temporale (all, 24h, 7d, 30d)
    - sort: campo ordinamento (created_at, state, total_points_imported, search_value)
    - order: direzione (asc, desc)
    - page: numero pagina (default 1)
    """
    from datetime import datetime, timedelta
    from sqlalchemy import text

    db: Session = SessionLocal()
    try:
        # Query base
        query = db.query(CatalogImport)

        # Filtro visibilità base (superuser vede tutto, altri solo i propri)
        if current_user.role != 'superuser':
            query = query.filter(CatalogImport.requested_by == current_user.id)

        # Recupera parametri filtro
        state = request.args.get('state', 'all')
        association_id = request.args.get('association_id', type=int) if current_user.role == 'superuser' else None
        date_filter = request.args.get('date_filter', 'all')
        sort_by = request.args.get('sort', 'created_at')
        sort_order = request.args.get('order', 'desc')
        page = request.args.get('page', 1, type=int)

        # Filtro stato
        if state and state != 'all':
            query = query.filter(CatalogImport.state == state)

        # Filtro associazione (solo superuser)
        if association_id and current_user.role == 'superuser':
            query = query.filter(CatalogImport.target_association_id == association_id)

        # Filtro temporale
        if date_filter in ['24h', '7d', '30d']:
            cutoff_mapping = {'24h': 1, '7d': 7, '30d': 30}
            cutoff = datetime.utcnow() - timedelta(days=cutoff_mapping[date_filter])
            query = query.filter(CatalogImport.created_at >= cutoff)

        # Ordinamento
        sortable_fields = {
            'created_at': CatalogImport.created_at,
            'state': CatalogImport.state,
            'total_points_imported': CatalogImport.total_points_imported,
            'search_value': CatalogImport.search_value,
        }

        if sort_by not in sortable_fields:
            sort_by = 'created_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'

        order_column = sortable_fields[sort_by]
        if sort_order == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginazione
        per_page = 50
        total = query.count()
        imports = query.limit(per_page).offset((page - 1) * per_page).all()

        # Conteggio stelle per ogni import
        import_stars_count = {}
        if imports:
            import_ids = [imp.id for imp in imports]
            placeholders = ','.join(str(id) for id in import_ids)

            # Per admin/analyst: conta solo stelle pubbliche (association_id_owner IS NULL)
            # o della loro associazione. Per superuser: conta tutte.
            if current_user.role == 'superuser':
                association_filter = ""
            else:
                association_filter = f"""
                    AND (association_id_owner IS NULL OR association_id_owner = '{current_user.association_id}')
                """

            stars_query = text(f"""
                SELECT catalog_import_id, COUNT(DISTINCT Source) as star_count
                FROM Cataloghi_esterni
                WHERE catalog_import_id IN ({placeholders})
                AND Source IS NOT NULL
                {association_filter}
                GROUP BY catalog_import_id
            """)

            results = db.execute(stars_query).fetchall()
            import_stars_count = {row.catalog_import_id: row.star_count for row in results}

            # Ensure all imports have entry (default to 0 if no rows)
            for imp_id in import_ids:
                if imp_id not in import_stars_count:
                    import_stars_count[imp_id] = 0

        # Carica lista associazioni per dropdown (solo superuser)
        associations = []
        if current_user.role == 'superuser':
            associations = db.query(Association).filter(
                Association.is_active == True
            ).order_by(Association.name).all()

        # Per admin/analyst: carica la lista dei progetti assegnati all'utente (per QLP upload)
        assigned_projects = None
        if current_user.role in ['analyst', 'admin']:
            assigned_projects = db.query(Project).filter(
                Project.assigned_to == current_user.id,
                Project.association_id == current_user.association_id,
                Project.state.in_(['assigned', 'in_review', 'active'])
            ).order_by(Project.project_code).all()

        return render_template(
            'admin/external_catalogs/search.html',
            available_catalogs=get_available_catalogs(),
            imports=imports,
            import_stars_count=import_stars_count,
            total=total,
            page=page,
            per_page=per_page,
            assigned_projects=assigned_projects,
            associations=associations,
            is_superuser=current_user.role == 'superuser',
            # Parametri correnti per preservare stato
            current_state=state,
            current_association_id=association_id,
            current_date_filter=date_filter,
            current_sort=sort_by,
            current_order=sort_order,
        )
    finally:
        db.close()


@admin_bp.route('/api/external-catalogs/search', methods=['POST'])
@login_required
@admin_required('admin')
def api_search_catalogs():
    """
    API: Avvia ricerca su cataloghi esterni.

    Solo admin e superuser possono cercare nuove stelle.
    Gli analyst devono usare l'upload file per stelle già assegnate.

    Body JSON:
    - ra: float (gradi, required)
    - dec: float (gradi, required)
    - radius_arcsec: float (default 5.0)
    - gaia_id: str (opzionale)
    - catalogs: list[str] (opzionale, default tutti)

    Returns:
        JSON con import_id e risultati preview per catalogo
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    # Validazione coordinate
    ra = data.get('ra')
    dec = data.get('dec')

    if ra is None or dec is None:
        return jsonify({'error': 'ra e dec sono obbligatori'}), 400

    try:
        ra = float(ra)
        dec = float(dec)
    except (ValueError, TypeError):
        return jsonify({'error': 'Coordinate non valide'}), 400

    if not (0 <= ra <= 360):
        return jsonify({'error': 'RA deve essere tra 0 e 360'}), 400
    if not (-90 <= dec <= 90):
        return jsonify({'error': 'Dec deve essere tra -90 e +90'}), 400

    radius = float(data.get('radius_arcsec', 5.0))
    gaia_id = data.get('gaia_id')
    catalogs = data.get('catalogs')  # None = tutti

    try:
        import_record, results = search_external_catalogs(
            ra=ra,
            dec=dec,
            radius_arcsec=radius,
            gaia_id=gaia_id,
            catalogs=catalogs,
            user_id=current_user.id,
            user_email=current_user.email
        )

        # Formatta risultati per JSON
        results_json = {}
        for catalog_name, result in results.items():
            results_json[catalog_name] = result.to_dict()

        return jsonify({
            'success': True,
            'import_id': import_record.id,
            'total_points': import_record.total_points_available,
            'catalogs_with_data': import_record.catalogs_with_data,
            'resolved_gaia_id': import_record.resolved_gaia_id,
            'results': results_json
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Errore durante la ricerca: {str(e)}'}), 500


@admin_bp.route('/api/external-catalogs/<int:import_id>/import', methods=['POST'])
@login_required
@admin_required('admin')
def api_import_data(import_id):
    """
    API: Importa dati selezionati in database locale.

    Solo admin e superuser possono importare da cataloghi esterni.
    Gli analyst usano l'upload file.

    Body JSON:
    - selected_catalogs: list[str] - cataloghi da importare (required)
    - gaia_id: str - Gaia ID per associazione dati (required)

    Returns:
        JSON con success e points_imported
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    selected_catalogs = data.get('selected_catalogs', [])
    gaia_id = data.get('gaia_id')

    if not selected_catalogs:
        return jsonify({'error': 'Seleziona almeno un catalogo'}), 400

    if not gaia_id:
        return jsonify({'error': 'gaia_id è obbligatorio'}), 400

    # Verifica permessi
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        # Solo chi ha creato o superuser può importare
        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            return jsonify({'error': 'Non autorizzato'}), 403
    finally:
        db.close()

    # Per admin (non superuser): crea automaticamente un progetto e dati appartengono all'associazione
    # Per superuser: i dati vanno nel "bacino centrale" senza progetto
    auto_create_project = current_user.role != 'superuser'
    association_id = current_user.association_id if auto_create_project else None
    association_id_owner = current_user.association_id if current_user.role != 'superuser' else None

    success, error, points, created_project = import_selected_data(
        import_id=import_id,
        selected_catalogs=selected_catalogs,
        gaia_id=gaia_id,
        user_id=current_user.id,
        user_email=current_user.email,
        association_id=association_id,
        auto_create_project=auto_create_project,
        association_id_owner=association_id_owner
    )

    if not success:
        return jsonify({'error': error}), 400

    response_data = {
        'success': True,
        'points_imported': points,
        'message': f'Importati {points} punti fotometrici'
    }

    # Se è stato creato un progetto, aggiungi le info
    if created_project:
        response_data['project_created'] = True
        response_data['project_id'] = created_project.id
        response_data['project_code'] = created_project.project_code
        response_data['message'] += f' - Creato progetto {created_project.project_code}'

    return jsonify(response_data)


@admin_bp.route('/api/external-catalogs/<int:import_id>/create-project', methods=['POST'])
@login_required
@superuser_required
@audit_action('project_created_from_import', 'project')
def api_create_project_from_import(import_id):
    """
    API: Crea Project AGATA da import completato.

    Solo superuser può creare Project e assegnarlo a un'associazione.

    Body JSON:
    - association_id: int - associazione target (required)
    - title: str (opzionale)

    Returns:
        JSON con project_id e project_code
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    association_id = data.get('association_id')
    if not association_id:
        return jsonify({'error': 'association_id è obbligatorio'}), 400

    try:
        association_id = int(association_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'association_id non valido'}), 400

    success, error, project = create_project_from_import(
        import_id=import_id,
        association_id=association_id,
        user_id=current_user.id,
        user_email=current_user.email,
        title=data.get('title')
    )

    if not success:
        return jsonify({'error': error}), 400

    return jsonify({
        'success': True,
        'project_id': project.id,
        'project_code': project.project_code,
        'message': f'Creato progetto {project.project_code}'
    }), 201


@admin_bp.route('/api/external-catalogs/imports')
@login_required
@admin_required('analyst')
def api_list_imports():
    """
    API: Lista importazioni recenti.

    Query params:
    - state: filtra per stato (pending, preview, completed, etc.)
    - limit: numero risultati (default 50, max 200)

    Returns:
        JSON array di importazioni
    """
    state = request.args.get('state')
    limit = min(int(request.args.get('limit', 50)), 200)

    # Non-superuser vedono solo le proprie
    user_id = None if current_user.role == 'superuser' else current_user.id

    imports = list_imports(user_id=user_id, state=state, limit=limit)

    return jsonify([
        {
            'id': imp.id,
            'search_type': imp.search_type,
            'search_value': imp.search_value,
            'state': imp.state,
            'total_points_available': imp.total_points_available,
            'total_points_imported': imp.total_points_imported,
            'catalogs_queried': imp.catalogs_queried,
            'selected_catalogs': imp.selected_catalogs,
            'notes': imp.notes,
            'project_id': imp.project_id,
            'created_at': imp.created_at.isoformat() if imp.created_at else None,
            'completed_at': imp.completed_at.isoformat() if imp.completed_at else None,
        }
        for imp in imports
    ])


@admin_bp.route('/api/external-catalogs/<int:import_id>')
@login_required
@admin_required('analyst')
def api_get_import(import_id):
    """
    API: Dettaglio singolo import.

    Returns:
        JSON con tutti i dettagli dell'import
    """
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        # Verifica permessi
        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            return jsonify({'error': 'Non autorizzato'}), 403

        return jsonify({
            'id': import_record.id,
            'search_type': import_record.search_type,
            'search_value': import_record.search_value,
            'search_radius_arcsec': import_record.search_radius_arcsec,
            'resolved_ra': import_record.resolved_ra,
            'resolved_dec': import_record.resolved_dec,
            'resolved_gaia_id': import_record.resolved_gaia_id,
            'state': import_record.state,
            'total_points_available': import_record.total_points_available,
            'total_points_imported': import_record.total_points_imported,
            'catalogs_queried': import_record.catalogs_queried,
            'selected_catalogs': import_record.selected_catalogs,
            'error_message': import_record.error_message,
            'notes': import_record.notes,
            'project_id': import_record.project_id,
            'target_association_id': import_record.target_association_id,
            'created_at': import_record.created_at.isoformat() if import_record.created_at else None,
            'completed_at': import_record.completed_at.isoformat() if import_record.completed_at else None,
            'is_importable': import_record.is_importable,
            'can_create_project': import_record.can_create_project,
            'catalogs_with_data': import_record.catalogs_with_data,
        })

    finally:
        db.close()


@admin_bp.route('/api/external-catalogs/<int:import_id>/cancel', methods=['POST'])
@login_required
@admin_required('analyst')
def api_cancel_import(import_id):
    """
    API: Cancella un import in corso o in preview.

    Body JSON (opzionale):
    - reason: str - motivazione cancellazione

    Returns:
        JSON con success
    """
    data = request.get_json() or {}
    reason = data.get('reason')

    # Verifica permessi
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            return jsonify({'error': 'Non autorizzato'}), 403
    finally:
        db.close()

    success, error = cancel_import(import_id, current_user.id, reason)

    if not success:
        return jsonify({'error': error}), 400

    return jsonify({
        'success': True,
        'message': 'Import cancellato'
    })


@admin_bp.route('/api/external-catalogs/<int:import_id>/notes', methods=['PUT'])
@login_required
@admin_required('analyst')
def api_update_import_notes(import_id):
    """
    API: Aggiorna le note di un import.

    Permessi:
    - Chi ha creato l'import
    - Superuser

    Body JSON:
    - notes: str (può essere vuoto per cancellare)

    Returns:
        JSON con success e notes aggiornate
    """
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        # Verifica permessi
        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            return jsonify({'error': 'Non autorizzato'}), 403

        data = request.get_json() or {}
        notes = data.get('notes', '').strip()

        # Aggiorna notes (può essere vuoto)
        import_record.notes = notes if notes else None
        db.commit()

        return jsonify({
            'success': True,
            'import_id': import_record.id,
            'notes': import_record.notes,
            'message': 'Note aggiornate'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/external-catalogs/<int:import_id>/imported-stars')
@login_required
@admin_required('analyst')
def api_get_imported_stars(import_id):
    """
    API: Ottiene lista di tutte le stelle (Gaia ID) importate in questo specifico import.

    Legge dalla tabella Cataloghi_esterni usando il campo catalog_import_id per
    ottenere solo le stelle importate da questo import specifico.

    Returns:
        JSON con lista di Gaia ID unici importati
    """
    from sqlalchemy import text

    db: Session = SessionLocal()
    try:
        # Verifica che l'import esista
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        # Verifica permessi
        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            return jsonify({'error': 'Non autorizzato'}), 403

        # Query per ottenere Gaia ID unici di questo specifico import
        query = text("""
            SELECT DISTINCT Source FROM Cataloghi_esterni
            WHERE catalog_import_id = :import_id
            AND Source IS NOT NULL
            ORDER BY Source
        """)

        results = db.execute(query, {'import_id': import_id}).fetchall()
        gaia_ids = [str(row.Source) for row in results]

        return jsonify({
            'success': True,
            'stars': gaia_ids,
            'count': len(gaia_ids),
            'message': f'Trovate {len(gaia_ids)} stelle'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/external-catalogs/<int:import_id>')
@login_required
@admin_required('analyst')
def external_catalog_detail(import_id):
    """
    Pagina dettaglio import con opzioni per:
    - Preview dati per catalogo
    - Import selettivo
    - Creazione Project (solo superuser)
    """
    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            abort(404)

        # Verifica permessi
        if current_user.role != 'superuser' and import_record.requested_by != current_user.id:
            abort(403)

        # Get associations per form creazione project (solo superuser)
        associations = []
        if current_user.role == 'superuser':
            associations = db.query(Association).filter(
                Association.is_active == True
            ).order_by(Association.name).all()

        return render_template(
            'admin/external_catalogs/detail.html',
            import_record=import_record,
            associations=associations,
            is_superuser=current_user.role == 'superuser',
            available_catalogs=get_available_catalogs()
        )

    finally:
        db.close()


@admin_bp.route('/api/external-catalogs/<int:import_id>/delete-data', methods=['POST'])
@login_required
@superuser_required
def api_delete_import_data(import_id):
    """
    API: Cancella i dati importati dal database e resetta l'import.

    Solo superuser può cancellare i dati.
    Cancella i record da Cataloghi_esterni e resetta lo stato dell'import.

    Returns:
        JSON con success e count di record cancellati
    """
    from sqlalchemy import text

    db: Session = SessionLocal()
    try:
        import_record = db.query(CatalogImport).filter(CatalogImport.id == import_id).first()
        if not import_record:
            return jsonify({'error': 'Import non trovato'}), 404

        if import_record.state not in ('completed', 'failed'):
            return jsonify({'error': f'Import non in stato completato (stato: {import_record.state})'}), 400

        gaia_id = import_record.resolved_gaia_id
        if not gaia_id:
            return jsonify({'error': 'Nessun Gaia ID associato a questo import'}), 400

        # Converti gaia_id in numero per la query
        try:
            gaia_id_clean = ''.join(filter(str.isdigit, str(gaia_id)))
            source_id = int(gaia_id_clean) if gaia_id_clean else None
        except (ValueError, TypeError):
            return jsonify({'error': 'Gaia ID non valido'}), 400

        if source_id is None:
            return jsonify({'error': 'Impossibile convertire Gaia ID'}), 400

        # Cancella i dati dalla tabella Cataloghi_esterni
        # Cancella solo i dati dei cataloghi selezionati per questo import
        selected_catalogs = import_record.selected_catalogs or []
        deleted_count = 0

        if selected_catalogs:
            for catalog in selected_catalogs:
                delete_sql = text("""
                    DELETE FROM Cataloghi_esterni
                    WHERE Source = :source_id AND catalogo = :catalogo
                """)
                result = db.execute(delete_sql, {'source_id': source_id, 'catalogo': catalog})
                deleted_count += result.rowcount

        # Resetta lo stato dell'import
        import_record.state = 'preview'
        import_record.total_points_imported = 0
        import_record.completed_at = None
        import_record.project_id = None
        import_record.error_message = None

        db.commit()

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Cancellati {deleted_count} record da Cataloghi_esterni'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/external-catalogs/available-catalogs')
@login_required
@admin_required('analyst')
def api_available_catalogs():
    """
    API: Lista cataloghi disponibili.

    Returns:
        JSON array di nomi cataloghi
    """
    return jsonify({
        'catalogs': get_available_catalogs()
    })


@admin_bp.route('/api/external-catalogs/upload-file', methods=['POST'])
@login_required
@admin_required('analyst')
def api_upload_file():
    """
    API: Importa dati fotometrici da file caricato.

    Per analyst: richiede che abbiano un progetto assegnato con quel gaia_id.
    Per admin/superuser: nessuna restrizione.

    Form data:
    - file: File CSV/TXT con dati fotometrici (required)
    - gaia_id: Gaia DR3 ID per associazione (required)
    - time_col: Nome colonna tempo (opzionale, auto-detect)
    - mag_col: Nome colonna magnitudine (opzionale, auto-detect)
    - err_col: Nome colonna errore (opzionale, auto-detect)
    - time_format: Formato tempo - hjd, jd, mjd, bjd, btjd (default: hjd)
    - band: Banda fotometrica (opzionale)
    - ra: Right Ascension in gradi (opzionale)
    - dec: Declination in gradi (opzionale)

    Formato file supportato:
    - CSV/TXT con header contenente nomi colonne
    - Delimitatori: virgola, tab, spazio (auto-detect)
    - Commenti con # o // ignorati

    Esempio file:
        hjd,mag,mag_err
        2459000.5,12.34,0.02
        2459001.5,12.38,0.03

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
        return jsonify({'error': 'gaia_id è obbligatorio'}), 400

    # Per analyst: verifica che abbia un progetto assegnato con questo gaia_id
    if current_user.role not in ['admin', 'superuser']:
        db_check: Session = SessionLocal()
        try:
            from agata.auth_models import Project
            assigned_project = db_check.query(Project).filter(
                Project.gaia_id == str(gaia_id),
                Project.assigned_to == current_user.id,
                Project.state.in_(['assigned', 'in_review'])
            ).first()

            if not assigned_project:
                return jsonify({
                    'error': f'Non hai un progetto assegnato per Gaia ID {gaia_id}. '
                             'Puoi caricare dati solo per stelle che ti sono state assegnate.'
                }), 403
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
    catalog_name = request.form.get('catalog_name') or None

    # Nome catalogo: usa catalog_name se specificato, altrimenti nome file
    source_name = catalog_name or file.filename or 'upload'

    # Coordinate opzionali per metadata
    ra = None
    dec = None
    if request.form.get('ra'):
        try:
            ra = float(request.form.get('ra'))
        except (ValueError, TypeError):
            pass
    if request.form.get('dec'):
        try:
            dec = float(request.form.get('dec'))
        except (ValueError, TypeError):
            pass

    # Per admin/analyst (non superuser): crea automaticamente un progetto
    # Per superuser: i dati vanno nel "bacino centrale" senza progetto
    auto_create_project = current_user.role != 'superuser'
    association_id = current_user.association_id if auto_create_project else None

    # Esegui import
    success, error, points, import_record, created_project = import_from_file(
        file_content=file_content,
        gaia_id=gaia_id,
        user_id=current_user.id,
        user_email=current_user.email,
        time_col=time_col,
        mag_col=mag_col,
        err_col=err_col,
        time_format=time_format,
        band=band,
        source_name=source_name,
        ra=ra,
        dec=dec,
        association_id=association_id,
        auto_create_project=auto_create_project
    )

    if not success:
        return jsonify({'error': error}), 400

    response_data = {
        'success': True,
        'import_id': import_record.id if import_record else None,
        'points_imported': points,
        'source_name': source_name,
        'message': f'Importati {points} punti fotometrici da {source_name}'
    }

    # Se è stato creato un progetto, aggiungi le info
    if created_project:
        response_data['project_created'] = True
        response_data['project_id'] = created_project.id
        response_data['project_code'] = created_project.project_code
        response_data['message'] += f' - Creato progetto {created_project.project_code}'

    return jsonify(response_data)
