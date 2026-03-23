# agata/admin/routes/stars_catalog.py
"""
Stars Catalog Routes

Interfaccia admin per gestire le stelle nel catalogo locale (Cataloghi_esterni):
- Lista stelle raggruppate per Gaia ID
- Dettaglio stella con tutti i dati fotometrici
- Cancellazione dati stella
- Assegnazione stelle a associazioni (senza progetto)
- Creazione Project da stella assegnata

Workflow:
1. Superuser carica stelle -> dati in Cataloghi_esterni (bacino centrale)
2. Superuser assegna stella a associazione -> record in star_assignments
3. Admin vede stelle assegnate -> crea progetto quando decide di lavorarci
"""
from flask import render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, superuser_required, audit_action
from agata.auth_models import Association, Project, StarAssignment
from agata.auth_models.catalog_import import CatalogImport
from agata.db import SessionLocal
from agata.admin.services.slack_service import get_slack_service

import logging
logger = logging.getLogger(__name__)


@admin_bp.route('/stars-catalog')
@login_required
@admin_required('analyst')  # Superuser, admin, reviewer, e analyst
def stars_catalog_page():
    """
    Pagina principale catalogo stelle.

    Mostra lista stelle raggruppate per Gaia ID con statistiche.
    - Superuser: vede tutte le stelle del bacino centrale, può assegnare a associazioni
    - Admin/Reviewer associazione: vede stelle assegnate alla propria associazione (con o senza progetto)
    - Analyst: vede solo stelle con progetti assegnati a lui

    Query params:
    - association_id: filtro associazione (solo superuser)
    - state: 'all', 'unassigned', 'assigned', 'with_project'
    - date_filter: 'all', '24h', '7d' (ultime 24h, ultima settimana)
    - catalog: filtro per catalogo
    - gaia_id: cerca per Gaia ID
    - sort: 'gaia_id', 'points', 'catalogs', 'date'
    - order: 'asc', 'desc'
    - page: paginazione
    """
    from datetime import datetime, timedelta

    db: Session = SessionLocal()
    try:
        is_superuser = current_user.role == 'superuser'
        is_admin = current_user.role == 'admin'
        is_reviewer = current_user.role == 'reviewer'
        is_analyst = current_user.role == 'analyst'

        # Filtro associazione (da query param per superuser)
        filter_association_id = request.args.get('association_id', type=int)

        # Non-superuser: forza filtro sulla propria associazione
        if not is_superuser:
            filter_association_id = current_user.association_id

        # Parametri filtri e ordinamento
        state_filter = request.args.get('state', 'all')  # NEW: stato filter
        date_filter = request.args.get('date_filter', 'all')  # NEW: date filter
        project_filter = request.args.get('project_filter', 'all')  # NEW: filtro progetto
        catalog_filter = request.args.get('catalog', '')
        import_filter = request.args.get('import_id', '', type=str)  # NEW: filtro import
        gaia_search = request.args.get('gaia_id', '')
        sort_by = request.args.get('sort', 'updated_at')
        sort_order = request.args.get('order', 'desc')
        page = request.args.get('page', 1, type=int)

        # Controlla se l'utente ha esplicitamente selezionato un filtro
        # (cioè se 'state', 'import_id', 'catalog', 'gaia_id' è presente nella query string)
        has_selected_filter = 'state' in request.args or 'import_id' in request.args or 'catalog' in request.args or 'gaia_id' in request.args

        # Se superuser non ha selezionato alcun filtro, non caricare stelle
        should_load_stars = True
        if is_superuser and not has_selected_filter and date_filter == 'all' and not catalog_filter and not gaia_search and not import_filter:
            should_load_stars = False

        # Admin: default mostra stelle senza progetti
        if is_admin and state_filter == 'all' and not has_selected_filter:
            state_filter = 'assigned'  # Mostra stelle CON assegnazioni ma SENZA progetto

        # Analyst: default mostra stelle assegnate all'analyst (già filtrate dalla query)
        if is_analyst and project_filter == 'all':
            project_filter = 'all'  # Mostra solo i tuoi progetti

        # Lista associazioni per dropdown (solo superuser)
        associations = []
        if is_superuser:
            associations = db.query(Association).filter(
                Association.is_active == True
            ).order_by(Association.name).all()

        # Determina quale dataset di stelle mostrare
        stars_raw = []
        all_catalogs = set()
        result = []

        # Costruisci WHERE clause per il filtro import se presente
        import_where_clause = ""
        if import_filter:
            try:
                import_id = int(import_filter)
                import_where_clause = f" AND catalog_import_id = {import_id}"
            except ValueError:
                pass

        # Se superuser non ha selezionato nulla, non caricare stelle
        if should_load_stars and is_superuser:
            # SUPERUSER: mostra stelle del bacino centrale
            # Se filter_association_id è set: mostra solo stelle assegnate a quella associazione
            # Se filter_association_id è None: mostra TUTTE le stelle (bacino centrale intero)

            if filter_association_id:
                # Mostra solo stelle assegnate a questa associazione
                assigned_gaia_ids = db.query(StarAssignment.gaia_id).filter(
                    StarAssignment.association_id == filter_association_id
                ).all()
                gaia_ids_assigned = [row.gaia_id for row in assigned_gaia_ids]

                if gaia_ids_assigned:
                    placeholders = ','.join([f':gaia_{i}' for i in range(len(gaia_ids_assigned))])
                    query_params = {f'gaia_{i}': gid for i, gid in enumerate(gaia_ids_assigned)}
                    query_params['filter_assoc_id'] = filter_association_id

                    stars_query = text(f"""
                        SELECT DISTINCT
                            ce.Source as gaia_id,
                            COUNT(*) as total_points,
                            COUNT(DISTINCT ce.catalogo) as num_catalogs,
                            GROUP_CONCAT(DISTINCT ce.catalogo ORDER BY ce.catalogo) as catalogs,
                            MIN(ce.hjd) as min_hjd,
                            MAX(ce.hjd) as max_hjd,
                            MIN(ce.Vmag) as min_mag,
                            MAX(ce.Vmag) as max_mag,
                            DATE(MAX(ci.created_at)) as last_data_date
                        FROM Cataloghi_esterni ce
                        LEFT JOIN agata_catalog_imports ci ON ce.catalog_import_id = ci.id
                        WHERE ce.Source IN ({placeholders})
                          AND (ce.association_id_owner IS NULL OR ce.association_id_owner = :filter_assoc_id)
                          {import_where_clause}
                        GROUP BY ce.Source
                    """)
                    result = db.execute(stars_query, query_params)
                else:
                    # Nessuna stella assegnata a questa associazione
                    result = []
            else:
                # Bacino centrale: TUTTE le stelle (mostra solo dati centrali)
                stars_query = text(f"""
                    SELECT DISTINCT
                        ce.Source as gaia_id,
                        COUNT(*) as total_points,
                        COUNT(DISTINCT ce.catalogo) as num_catalogs,
                        GROUP_CONCAT(DISTINCT ce.catalogo ORDER BY ce.catalogo) as catalogs,
                        MIN(ce.hjd) as min_hjd,
                        MAX(ce.hjd) as max_hjd,
                        MIN(ce.Vmag) as min_mag,
                        MAX(ce.Vmag) as max_mag,
                        DATE(MAX(ci.created_at)) as last_data_date
                    FROM Cataloghi_esterni ce
                    LEFT JOIN agata_catalog_imports ci ON ce.catalog_import_id = ci.id
                    WHERE ce.association_id_owner IS NULL
                      {import_where_clause}
                    GROUP BY ce.Source
                """)
                result = db.execute(stars_query)

        elif should_load_stars:
            # ADMIN/REVIEWER/ANALYST: mostra stelle della propria associazione
            if is_analyst:
                # ANALYST: mostra stelle con progetti in base al filtro project_filter
                # project_filter può essere:
                # - 'all': progetti assegnati a me
                # - 'assigned_to_others': progetti assegnati ad altri dell'associazione

                if project_filter == 'assigned_to_others':
                    # Mostra solo stelle con progetti assegnati ad ALTRI
                    projects = db.query(Project).filter(
                        Project.assigned_to != current_user.id,
                        Project.assigned_to.isnot(None),  # Escludi progetti non assegnati
                        Project.association_id == filter_association_id,
                        Project.state != 'cancelled'
                    ).all()
                else:
                    # Default: mostra stelle con progetti assegnati a ME (project_filter == 'all')
                    projects = db.query(Project).filter(
                        Project.assigned_to == current_user.id,
                        Project.association_id == filter_association_id,
                        Project.state != 'cancelled'
                    ).all()
                gaia_ids_assigned = set(p.gaia_id for p in projects)
            else:
                # ADMIN/REVIEWER: mostra tutte le stelle assegnate alla propria associazione
                assignments = db.query(StarAssignment).filter(
                    StarAssignment.association_id == filter_association_id
                ).all()
                gaia_ids_assigned = set(a.gaia_id for a in assignments)

            result = []
            if gaia_ids_assigned:
                # Query dati fotometrici per le stelle assegnate
                placeholders = ','.join([f':gaia_{i}' for i in range(len(gaia_ids_assigned))])
                query_params = {f'gaia_{i}': gid for i, gid in enumerate(gaia_ids_assigned)}

                stars_query = text(f"""
                    SELECT
                        ce.Source as gaia_id,
                        COUNT(*) as total_points,
                        COUNT(DISTINCT ce.catalogo) as num_catalogs,
                        GROUP_CONCAT(DISTINCT ce.catalogo ORDER BY ce.catalogo) as catalogs,
                        MIN(ce.hjd) as min_hjd,
                        MAX(ce.hjd) as max_hjd,
                        MIN(ce.Vmag) as min_mag,
                        MAX(ce.Vmag) as max_mag,
                        DATE(MAX(ci.created_at)) as last_data_date
                    FROM Cataloghi_esterni ce
                    LEFT JOIN agata_catalog_imports ci ON ce.catalog_import_id = ci.id
                    WHERE ce.Source IN ({placeholders})
                      AND (ce.association_id_owner IS NULL OR ce.association_id_owner = :filter_assoc_id)
                      {import_where_clause}
                    GROUP BY ce.Source
                """)

                query_params['filter_assoc_id'] = filter_association_id
                result = db.execute(stars_query, query_params)

        # Converti result in lista per poterla iterare più volte
        result = list(result) if result else []

        # Recupera TUTTI gli import_ids una sola volta (ottimizzazione)
        all_gaia_ids = [row.gaia_id for row in result]
        import_cache = {}  # {gaia_id: {'ids': [...], 'info': {...}}}

        if all_gaia_ids:
            # Query unica per ottenere tutti gli import_ids
            placeholders = ','.join([f':gaia_{i}' for i in range(len(all_gaia_ids))])
            query_params_imports = {f'gaia_{i}': gid for i, gid in enumerate(all_gaia_ids)}

            imports_data = db.execute(
                text(f"""
                    SELECT Source, catalog_import_id
                    FROM Cataloghi_esterni
                    WHERE Source IN ({placeholders}) AND catalog_import_id IS NOT NULL
                      {import_where_clause}
                    GROUP BY Source, catalog_import_id
                """),
                query_params_imports
            ).fetchall()

            # Costruisci cache e raccogli import_ids unici per load
            import_ids_to_load = set()
            for gaia_id_row, imp_id in imports_data:
                if imp_id:
                    gaia_id_str = str(gaia_id_row)  # Converti a string per coerenza
                    if gaia_id_str not in import_cache:
                        import_cache[gaia_id_str] = {'ids': [], 'info': None}
                    import_cache[gaia_id_str]['ids'].append(imp_id)
                    import_ids_to_load.add(imp_id)

            # Load info per tutti gli import in una sola query
            if import_ids_to_load:
                import_ids_list = list(import_ids_to_load)
                import_placeholders = ','.join([f':imp_{i}' for i in range(len(import_ids_list))])
                import_query_params = {f'imp_{i}': imp_id for i, imp_id in enumerate(import_ids_list)}

                imports_info = db.execute(
                    text(f"""
                        SELECT id, search_type, search_value, created_at
                        FROM agata_catalog_imports
                        WHERE id IN ({import_placeholders})
                    """),
                    import_query_params
                ).fetchall()

                # Mappa info per import_id
                import_info_map = {}
                for imp_id, search_type, search_value, created_at in imports_info:
                    import_info_map[imp_id] = {
                        'id': imp_id,
                        'search_type': search_type,
                        'search_value': search_value,
                        'created_at': created_at.strftime('%d/%m/%Y %H:%M') if created_at else ''
                    }

                # Popola info nella cache
                for gaia_id_key in import_cache:
                    if import_cache[gaia_id_key]['ids']:
                        first_import_id = import_cache[gaia_id_key]['ids'][0]
                        if first_import_id in import_info_map:
                            import_cache[gaia_id_key]['info'] = import_info_map[first_import_id]

        # === NUOVO: Recupera VAST variable_type per tutte le stelle ===
        vast_cache = {}
        if all_gaia_ids:
            try:
                # Query VAST results: recupera variable_type e catalog_matches per ogni Gaia ID
                placeholders_gaia = ','.join([f':gaia_{i}' for i in range(len(all_gaia_ids))])
                query_params_vast = {f'gaia_{i}': int(gid) for i, gid in enumerate(all_gaia_ids)}

                vast_results = db.execute(
                    text(f"""
                        SELECT
                            gaia_source_id,
                            GROUP_CONCAT(DISTINCT variable_type SEPARATOR ',') as variable_types,
                            MAX(is_known_variable) as is_known_variable,
                            GROUP_CONCAT(DISTINCT catalog_matches SEPARATOR ';') as all_catalog_matches
                        FROM agata_vast_results
                        WHERE gaia_source_id IN ({placeholders_gaia})
                          AND is_valid = TRUE
                        GROUP BY gaia_source_id
                    """),
                    query_params_vast
                ).fetchall()

                # Costruisci cache: {gaia_id: {variable_types: [...], is_known_variable: bool, catalog_matches: [...]}}
                for row in vast_results:
                    gaia_id = str(row.gaia_source_id)
                    variable_types = [t.strip() for t in (row.variable_types or '').split(',') if t.strip()]
                    catalog_matches = [c.strip() for c in (row.all_catalog_matches or '').split(';') if c.strip()]

                    vast_cache[gaia_id] = {
                        'variable_types': variable_types,
                        'is_known_variable': bool(row.is_known_variable),
                        'catalog_matches': catalog_matches
                    }
            except Exception as e:
                logger.warning(f"Errore recupero VAST data: {e}")
                vast_cache = {}

        # === OTTIMIZZAZIONE: Batch loading StarAssignment e Project ===
        # Carica TUTTI gli StarAssignment e Project in 2 query invece di 683 query singole
        star_assignments_cache = {}  # {gaia_id: [StarAssignment, ...]}
        projects_cache = {}  # {gaia_id: Project}

        if all_gaia_ids:
            # Batch query 1: Carica TUTTI gli StarAssignment
            all_gaia_ids_str = [str(gid) for gid in all_gaia_ids]

            assignments_query = db.query(StarAssignment).filter(
                StarAssignment.gaia_id.in_(all_gaia_ids_str)
            )

            if not is_superuser:
                # Admin/Analyst: filtra per propria associazione
                assignments_query = assignments_query.filter(
                    StarAssignment.association_id == filter_association_id
                )

            all_assignments = assignments_query.all()

            # Costruisci cache: {gaia_id: [assignments]}
            for assignment in all_assignments:
                gaia_id_str = str(assignment.gaia_id)
                if gaia_id_str not in star_assignments_cache:
                    star_assignments_cache[gaia_id_str] = []
                star_assignments_cache[gaia_id_str].append(assignment)

            # Batch query 2: Carica TUTTI i Project
            projects_query = db.query(Project).filter(
                Project.gaia_id.in_(all_gaia_ids_str),
                Project.state != 'cancelled'
            )

            if not is_superuser:
                # Admin/Analyst: filtra per propria associazione
                projects_query = projects_query.filter(
                    Project.association_id == filter_association_id
                )

            all_projects = projects_query.all()

            # Costruisci cache: {gaia_id: Project} (prendi il primo, dovrebbe essere uno solo per stella)
            for project in all_projects:
                gaia_id_str = str(project.gaia_id)
                if gaia_id_str not in projects_cache:
                    projects_cache[gaia_id_str] = project

        for row in result:
            # Cataloghi lista (non raccogliere ancora, lo faremo dopo i filtri)
            catalogs_list = row.catalogs.split(',') if row.catalogs else []

            # Recupera assegnazioni dalla cache (no query!)
            all_assignments = star_assignments_cache.get(str(row.gaia_id), [])

            # Recupera progetto dalla cache (no query!)
            project = projects_cache.get(str(row.gaia_id), None)

            # Logica per abilitare azioni
            can_create_project = False
            if all_assignments and not project:
                if is_superuser:
                    # Superuser può creare progetto per qualunque assegnazione
                    can_create_project = True
                elif is_admin:
                    # Admin può creare progetto se questa stella ha assegnazione alla sua associazione
                    can_create_project = any(
                        a.association_id == filter_association_id for a in all_assignments
                    )

            # Recupera import_ids e info dalla cache (no query!)
            import_ids = import_cache.get(str(row.gaia_id), {}).get('ids', [])
            import_info = import_cache.get(str(row.gaia_id), {}).get('info')

            stars_raw.append({
                'gaia_id': row.gaia_id,
                'total_points': row.total_points,
                'num_catalogs': row.num_catalogs,
                'catalogs': catalogs_list,
                'min_hjd': row.min_hjd,
                'max_hjd': row.max_hjd,
                'min_mag': row.min_mag,
                'max_mag': row.max_mag,
                'last_data_date': row.last_data_date,
                # Tutte le assegnazioni per questa stella
                'all_assignments': [
                    {
                        'id': a.id,
                        'association_id': a.association_id,
                        'association_name': a.association.name,
                        'assigned_at': a.assigned_at.strftime('%Y-%m-%d')
                    }
                    for a in all_assignments
                ],
                # Info progetto
                'project_id': project.id if project else None,
                'project_code': project.project_code if project else None,
                'project_state': project.state if project else None,
                'project_association': project.association.name if project else None,
                # Info import
                'import_info': import_info,
                'import_ids': import_ids,
                # NUOVO: Info VAST variable_type
                'variable_types': vast_cache.get(str(row.gaia_id), {}).get('variable_types', []),
                'is_known_variable': vast_cache.get(str(row.gaia_id), {}).get('is_known_variable', False),
                'catalog_matches': vast_cache.get(str(row.gaia_id), {}).get('catalog_matches', []),
                # Flag per azioni
                'can_create_project': can_create_project,
                'can_self_assign': False
            })

        # Applica filtri
        stars = stars_raw

        # Filtro di stato (all, unassigned, assigned, with_project)
        if state_filter == 'unassigned':
            # Stelle SENZA assegnazioni
            stars = [s for s in stars if not s['all_assignments']]
        elif state_filter == 'assigned':
            # Stelle CON assegnazioni ma SENZA progetto
            stars = [s for s in stars if s['all_assignments'] and not s['project_id']]
        elif state_filter == 'with_project':
            # Stelle CON progetto
            stars = [s for s in stars if s['project_id']]
        # 'all' non filtra nulla

        # Filtro per data caricamento (basato su last_data_date - data import)
        if date_filter in ['24h', '7d']:
            now = datetime.utcnow().date()
            if date_filter == '24h':
                cutoff_date = now - timedelta(days=1)
            else:  # '7d'
                cutoff_date = now - timedelta(days=7)

            filtered_stars = []
            for s in stars:
                # Mostra SOLO le stelle che hanno un import_id (hanno data vera)
                # Le stelle senza import_id non hanno data di importazione tracciata
                if s['import_ids'] and len(s['import_ids']) > 0:  # Solo stelle con import associato
                    if s['last_data_date']:
                        # Converti a date se necessario
                        if isinstance(s['last_data_date'], str):
                            star_date = datetime.strptime(s['last_data_date'], '%Y-%m-%d').date()
                        else:
                            star_date = s['last_data_date']

                        if star_date >= cutoff_date:
                            filtered_stars.append(s)

            stars = filtered_stars

        # Filtro per catalogo
        if catalog_filter:
            stars = [s for s in stars if catalog_filter in s['catalogs']]

        # NUOVO: Filtro per variable_type (VAST)
        variable_type_filter = request.args.get('variable_type', '')
        if variable_type_filter:
            selected_types = [t.strip() for t in variable_type_filter.split(',') if t.strip()]
            stars = [s for s in stars if any(vt in s['variable_types'] for vt in selected_types)]

        # NUOVO: Filtro per variabili note
        known_var_filter = request.args.get('known_variables_only', '').lower() == 'true'
        if known_var_filter:
            stars = [s for s in stars if s['is_known_variable']]

        # Nota: Il filtro per import è già incorporato nella query SQL per performance

        # Filtro per progetto (admin/analyst specifico)
        if is_admin or is_reviewer:
            # Admin/Reviewer: filtro 'no_project' mostra stelle senza progetto assegnate alla loro associazione
            if project_filter == 'no_project':
                stars = [s for s in stars if not s['project_id']]
            # 'all' non filtra nulla
        elif is_analyst:
            # Analyst: filtro 'assigned_to_others' mostra progetti assegnati a altri analyst
            if project_filter == 'assigned_to_others':
                # Prende stelle che hanno un progetto assegnato ma NON al current_user
                stars = [s for s in stars if s['project_id']]
            # 'all' mostra solo i tuoi progetti (già filtrato nella query iniziale)

        # Ricerca per Gaia ID
        if gaia_search:
            stars = [s for s in stars if gaia_search.lower() in str(s['gaia_id']).lower()]

        # Ordinamento
        reverse_order = sort_order == 'desc'
        if sort_by == 'gaia_id':
            stars = sorted(stars, key=lambda x: int(x['gaia_id']) if str(x['gaia_id']).isdigit() else 0, reverse=reverse_order)
        elif sort_by == 'points':
            stars = sorted(stars, key=lambda x: x['total_points'], reverse=reverse_order)
        elif sort_by == 'catalogs':
            stars = sorted(stars, key=lambda x: x['num_catalogs'], reverse=reverse_order)
        elif sort_by == 'date':
            # Ordina per data - gestisci date objects da SQL
            from datetime import date as date_type
            def sort_date_key(x):
                date_val = x['last_data_date']
                if date_val is None:
                    return date_type.min if reverse_order else date_type.max
                if isinstance(date_val, str):
                    try:
                        return datetime.strptime(date_val, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        return date_type.min if reverse_order else date_type.max
                if isinstance(date_val, datetime):
                    return date_val.date()
                return date_val  # Già un date object
            stars = sorted(stars, key=sort_date_key, reverse=reverse_order)
        elif sort_by == 'min_mag':
            stars = sorted(stars, key=lambda x: x['min_mag'] if x['min_mag'] is not None else 999, reverse=reverse_order)
        elif sort_by == 'max_mag':
            stars = sorted(stars, key=lambda x: x['max_mag'] if x['max_mag'] is not None else 999, reverse=reverse_order)
        elif sort_by == 'avg_mag':
            # Calcola magnitudine media per ordinamento
            stars = sorted(stars, key=lambda x: ((x['min_mag'] or 0) + (x['max_mag'] or 0)) / 2 if (x['min_mag'] is not None or x['max_mag'] is not None) else 999, reverse=reverse_order)
        else:  # updated_at (default) - ordina numericamente per data come 'date'
            from datetime import date as date_type
            def sort_date_key(x):
                date_val = x['last_data_date']
                if date_val is None:
                    return date_type.min if reverse_order else date_type.max
                if isinstance(date_val, str):
                    try:
                        return datetime.strptime(date_val, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        return date_type.min if reverse_order else date_type.max
                if isinstance(date_val, datetime):
                    return date_val.date()
                return date_val  # Già un date object
            stars = sorted(stars, key=sort_date_key, reverse=reverse_order)

        # Raccogli cataloghi dalle stelle FILTRATE (non da tutte)
        for star in stars:
            for catalog in star['catalogs']:
                all_catalogs.add(catalog)

        # Recupera lista import per il dropdown
        available_imports = []
        if not is_analyst:  # Solo superuser, admin, reviewer vedono import
            try:
                imports_query = db.query(CatalogImport).filter(
                    CatalogImport.state == 'completed'
                ).order_by(CatalogImport.created_at.desc()).all()
                available_imports = imports_query
            except Exception as e:
                logger.error(f"Errore nel recupero degli import: {e}")

        # Paginazione
        per_page = 50
        total = len(stars)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stars_paginated = stars[start_idx:end_idx]

        # Lista cataloghi disponibili per filtro
        available_catalogs = sorted(list(all_catalogs))

        # NUOVO: Raccogli tutti gli unique variable_type dalle stelle FILTRATE
        all_variable_types = set()
        for star in stars:
            for vtype in star['variable_types']:
                if vtype:
                    all_variable_types.add(vtype)
        available_variable_types = sorted(list(all_variable_types))

        return render_template(
            'admin/stars_catalog/list.html',
            stars=stars_paginated,
            associations=associations,
            available_catalogs=available_catalogs,
            available_imports=available_imports,
            available_variable_types=available_variable_types,
            filter_association_id=filter_association_id,
            state_filter=state_filter,
            date_filter=date_filter,
            project_filter=project_filter,
            catalog_filter=catalog_filter,
            variable_type_filter=variable_type_filter,
            known_var_filter=known_var_filter,
            import_filter=import_filter,
            gaia_search=gaia_search,
            sort_by=sort_by,
            sort_order=sort_order,
            current_page=page,
            total_stars=total,
            per_page=per_page,
            is_superuser=is_superuser,
            is_admin=is_admin,
            should_load_stars=should_load_stars,
            is_analyst=is_analyst
        )
    finally:
        db.close()


@admin_bp.route('/stars-catalog/<gaia_id>')
@login_required
@admin_required('analyst')
def star_detail(gaia_id):
    """
    Dettaglio singola stella con tutti i dati per catalogo.

    - Superuser: vede tutte le assegnazioni e progetti, può assegnare a nuove associazioni
    - Admin associazione: vede assegnazione e progetto della propria associazione
    - Analyst: vede progetti della propria associazione
    """
    db: Session = SessionLocal()
    try:
        is_superuser = current_user.role == 'superuser'
        is_admin = current_user.role == 'admin'

        # Verifica che la stella esista (e sia accessible)
        check_query = text("""
            SELECT COUNT(*) as cnt FROM Cataloghi_esterni
            WHERE Source = :gaia_id
              AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
        """)
        check_params = {
            'gaia_id': gaia_id,
            'user_assoc_id': current_user.association_id if not is_superuser else None,
            'is_superuser': 1 if is_superuser else 0
        }
        result = db.execute(check_query, check_params).fetchone()
        if not result or result.cnt == 0:
            abort(404)

        # Dati per catalogo (filtra per association_id_owner)
        # Per superuser: include anche l'association_id_owner per mostrare chi ha caricato
        catalogs_query = text("""
            SELECT
                catalogo,
                association_id_owner,
                COUNT(*) as points,
                MIN(hjd) as min_hjd,
                MAX(hjd) as max_hjd,
                MIN(Vmag) as min_mag,
                MAX(Vmag) as max_mag,
                AVG(Vmag) as avg_mag
            FROM Cataloghi_esterni
            WHERE Source = :gaia_id
              AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
            GROUP BY catalogo, association_id_owner
            ORDER BY points DESC
        """)

        catalog_params = {
            'gaia_id': gaia_id,
            'user_assoc_id': current_user.association_id if not is_superuser else None,
            'is_superuser': 1 if is_superuser else 0
        }
        catalogs_result = db.execute(catalogs_query, catalog_params)
        catalogs = []
        total_points = 0
        for row in catalogs_result:
            catalog_entry = {
                'name': row.catalogo,
                'points': row.points,
                'min_hjd': row.min_hjd,
                'max_hjd': row.max_hjd,
                'min_mag': row.min_mag,
                'max_mag': row.max_mag,
                'avg_mag': row.avg_mag,
            }

            # Se superuser: mostra quale associazione ha caricato (NULL = bacino centrale)
            if is_superuser and row.association_id_owner is not None:
                association = db.query(Association).filter(
                    Association.id == row.association_id_owner
                ).first()
                if association:
                    catalog_entry['owner_association'] = association.name
                    catalog_entry['owner_association_id'] = association.id
            elif is_superuser and row.association_id_owner is None:
                catalog_entry['owner_association'] = 'Bacino centrale'
                catalog_entry['owner_association_id'] = None

            catalogs.append(catalog_entry)
            total_points += row.points

        # Import associato - cerca prima via foreign key (catalog_import_id), poi via resolved_gaia_id
        import_ids_query = db.execute(
            text("SELECT DISTINCT catalog_import_id FROM Cataloghi_esterni WHERE Source = :gaia_id AND catalog_import_id IS NOT NULL LIMIT 1"),
            {"gaia_id": gaia_id}
        ).fetchone()

        import_record = None
        if import_ids_query and import_ids_query[0]:
            import_record = db.query(CatalogImport).filter(
                CatalogImport.id == import_ids_query[0]
            ).first()

        # Fallback: cerca via resolved_gaia_id (per import vecchi senza foreign key)
        if not import_record:
            import_record = db.query(CatalogImport).filter(
                CatalogImport.resolved_gaia_id == str(gaia_id)
            ).order_by(CatalogImport.created_at.desc()).first()

        # Assegnazioni per questa stella
        assignments_query = db.query(StarAssignment).filter(
            StarAssignment.gaia_id == str(gaia_id)
        )

        if not is_superuser:
            assignments_query = assignments_query.filter(
                StarAssignment.association_id == current_user.association_id
            )

        assignments = assignments_query.order_by(StarAssignment.assigned_at.desc()).all()

        # Progetti ATTIVI associati (escludi cancellati)
        # Superuser vede TUTTI i progetti per questa stella
        # Admin/Analyst vedono solo i progetti della loro associazione
        active_projects_query = db.query(Project).filter(
            Project.gaia_id == str(gaia_id),
            Project.state != 'cancelled'
        )

        if not is_superuser:
            active_projects_query = active_projects_query.filter(
                Project.association_id == current_user.association_id
            )

        active_projects = active_projects_query.order_by(Project.created_at.desc()).all()

        # Progetti cancellati (storico)
        cancelled_projects_query = db.query(Project).filter(
            Project.gaia_id == str(gaia_id),
            Project.state == 'cancelled'
        )

        if not is_superuser:
            cancelled_projects_query = cancelled_projects_query.filter(
                Project.association_id == current_user.association_id
            )

        cancelled_projects = cancelled_projects_query.order_by(Project.created_at.desc()).all()

        # Associazioni per form assegnazione (solo superuser)
        # Escludi associazioni che hanno già un'assegnazione per questa stella
        associations = []
        if is_superuser:
            assigned_assoc_ids = [a.association_id for a in db.query(StarAssignment).filter(
                StarAssignment.gaia_id == str(gaia_id)
            ).all()]

            associations = db.query(Association).filter(
                Association.is_active == True,
                ~Association.id.in_(assigned_assoc_ids) if assigned_assoc_ids else True
            ).order_by(Association.name).all()

        # Can create project if:
        # - Admin: has assignment without project to their own association
        # - Superuser: has any assignment without project (can create for any association)
        can_create_project = False
        my_assignment = None
        if is_superuser:
            # Superuser can create if there are any assignments without a project
            assignments_without_project = db.query(StarAssignment).filter(
                StarAssignment.gaia_id == str(gaia_id),
                StarAssignment.project_id == None
            ).first()
            can_create_project = assignments_without_project is not None
        elif is_admin:
            my_assignment = db.query(StarAssignment).filter(
                StarAssignment.gaia_id == str(gaia_id),
                StarAssignment.association_id == current_user.association_id,
                StarAssignment.project_id == None
            ).first()
            can_create_project = my_assignment is not None

        return render_template(
            'admin/stars_catalog/detail.html',
            gaia_id=gaia_id,
            catalogs=catalogs,
            total_points=total_points,
            import_record=import_record,
            assignments=assignments,
            active_projects=active_projects,
            cancelled_projects=cancelled_projects,
            associations=associations,
            is_superuser=is_superuser,
            is_admin=is_admin,
            can_create_project=can_create_project,
            my_assignment=my_assignment
        )
    finally:
        db.close()


@admin_bp.route('/api/stars-catalog/<gaia_id>/delete', methods=['POST'])
@login_required
@superuser_required
def api_delete_star_data(gaia_id):
    """
    API: Cancella tutti i dati di una stella dal catalogo.

    Body JSON (opzionale):
    - catalogs: list[str] - cataloghi specifici da cancellare (default: tutti)

    Returns:
        JSON con success e count di record cancellati
    """
    data = request.get_json() or {}
    catalogs_to_delete = data.get('catalogs')  # None = tutti

    db: Session = SessionLocal()
    try:
        # Converti gaia_id
        try:
            source_id = int(gaia_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Gaia ID non valido'}), 400

        # Cancella i dati
        if catalogs_to_delete:
            # Cancella solo cataloghi specificati
            deleted_count = 0
            for catalog in catalogs_to_delete:
                delete_sql = text("""
                    DELETE FROM Cataloghi_esterni
                    WHERE Source = :source_id AND catalogo = :catalogo
                """)
                result = db.execute(delete_sql, {'source_id': source_id, 'catalogo': catalog})
                deleted_count += result.rowcount
        else:
            # Cancella tutti i dati della stella
            delete_sql = text("""
                DELETE FROM Cataloghi_esterni WHERE Source = :source_id
            """)
            result = db.execute(delete_sql, {'source_id': source_id})
            deleted_count = result.rowcount

        db.commit()

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Cancellati {deleted_count} record'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/stars-catalog/bulk-assign', methods=['POST'])
@login_required
@superuser_required
@audit_action('stars_bulk_assigned', 'star_assignment')
def api_bulk_assign_stars():
    """
    API: Assegna multiple stelle a un'associazione (SENZA creare progetto).

    Il superuser assegna stelle alle associazioni. L'admin dell'associazione
    deciderà poi se creare progetti.

    Body JSON:
    - gaia_ids: list[str] - liste di Gaia ID da assegnare (required)
    - association_id: int - associazione target (required)
    - notes: str (opzionale)

    Returns:
        JSON con risultati assegnazione
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Body JSON richiesto'}), 400

    gaia_ids = data.get('gaia_ids')
    association_id = data.get('association_id')

    if not gaia_ids or not isinstance(gaia_ids, list) or len(gaia_ids) == 0:
        return jsonify({'error': 'gaia_ids è obbligatorio e deve essere una lista non vuota'}), 400
    if not association_id:
        return jsonify({'error': 'association_id è obbligatorio'}), 400

    try:
        association_id = int(association_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'association_id non valido'}), 400

    db: Session = SessionLocal()
    try:
        # Verifica associazione
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({'error': 'Associazione non trovata'}), 404

        successful = 0
        failed = []
        already_assigned = []

        for gaia_id in gaia_ids:
            try:
                # Verifica che la stella esista nel catalogo
                check_query = text("""
                    SELECT COUNT(*) as cnt FROM Cataloghi_esterni WHERE Source = :gaia_id
                """)
                result = db.execute(check_query, {'gaia_id': gaia_id}).fetchone()
                if not result or result.cnt == 0:
                    failed.append(f'{gaia_id}: stella non trovata nel catalogo')
                    continue

                # Verifica che non esista già un'assegnazione per questa stella + associazione
                existing = db.query(StarAssignment).filter(
                    StarAssignment.gaia_id == str(gaia_id),
                    StarAssignment.association_id == association_id
                ).first()
                if existing:
                    already_assigned.append(gaia_id)
                    continue

                # Crea l'assegnazione
                assignment = StarAssignment(
                    gaia_id=str(gaia_id),
                    association_id=association_id,
                    assigned_by=current_user.id,
                    notes=data.get('notes')
                )
                db.add(assignment)
                successful += 1

            except Exception as e:
                failed.append(f'{gaia_id}: {str(e)}')

        db.commit()

        response = {
            'success': True,
            'assigned': successful,
            'already_assigned': len(already_assigned),
            'failed': len(failed),
            'message': f'Assegnate {successful} stelle a {association.name}'
        }

        if failed:
            response['failed_details'] = failed
        if already_assigned:
            response['already_assigned_ids'] = already_assigned

        return jsonify(response), 201

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/stars-catalog/<gaia_id>/assign', methods=['POST'])
@login_required
@superuser_required
@audit_action('star_assigned', 'star_assignment')
def api_assign_star_to_association(gaia_id):
    """
    API: Assegna stella a un'associazione (SENZA creare progetto).

    Il superuser assegna stelle alle associazioni. L'admin dell'associazione
    deciderà poi se creare un progetto.

    Body JSON:
    - association_id: int - associazione target (required)
    - notes: str (opzionale)

    Returns:
        JSON con assignment_id
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

    db: Session = SessionLocal()
    try:
        # Verifica che la stella esista nel catalogo
        check_query = text("""
            SELECT COUNT(*) as cnt FROM Cataloghi_esterni WHERE Source = :gaia_id
        """)
        result = db.execute(check_query, {'gaia_id': gaia_id}).fetchone()
        if not result or result.cnt == 0:
            return jsonify({'error': 'Stella non trovata nel catalogo'}), 404

        # Verifica che non esista già un'assegnazione per questa stella + associazione
        existing = db.query(StarAssignment).filter(
            StarAssignment.gaia_id == str(gaia_id),
            StarAssignment.association_id == association_id
        ).first()
        if existing:
            return jsonify({
                'error': f'Stella già assegnata a questa associazione'
            }), 400

        # Verifica associazione
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({'error': 'Associazione non trovata'}), 404

        # Crea l'assegnazione
        assignment = StarAssignment(
            gaia_id=str(gaia_id),
            association_id=association_id,
            assigned_by=current_user.id,
            notes=data.get('notes')
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)

        # Notifica Slack (best-effort) - opzionale
        try:
            slack_service = get_slack_service()
            if slack_service and slack_service.is_configured():
                slack_service.notify_star_assigned(db, assignment, association)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack fallita per assegnazione stella {gaia_id}: {slack_error}")

        return jsonify({
            'success': True,
            'assignment_id': assignment.id,
            'message': f'Stella {gaia_id} assegnata a {association.name}'
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/stars-catalog/<gaia_id>/create-project', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_created_from_assignment', 'project')
def api_create_project_from_assignment(gaia_id):
    """
    API: Crea Project AGATA da stella assegnata.

    L'admin può creare un progetto solo se:
    - La stella è assegnata alla sua associazione
    - Non esiste già un progetto attivo per questa stella nella sua associazione

    Body JSON (opzionale):
    - title: str

    Returns:
        JSON con project_id e project_code
    """
    from datetime import datetime

    data = request.get_json() or {}

    db: Session = SessionLocal()
    try:
        # Verifica che la stella sia assegnata all'associazione dell'admin
        assignment = db.query(StarAssignment).filter(
            StarAssignment.gaia_id == str(gaia_id),
            StarAssignment.association_id == current_user.association_id
        ).first()

        if not assignment:
            return jsonify({
                'error': 'Stella non assegnata alla tua associazione'
            }), 403

        # Verifica che non esista già un progetto attivo
        existing = db.query(Project).filter(
            Project.gaia_id == str(gaia_id),
            Project.association_id == current_user.association_id,
            Project.state != 'cancelled'
        ).first()
        if existing:
            return jsonify({
                'error': f'Progetto già esistente: {existing.project_code}'
            }), 400

        # Verifica associazione
        association = db.query(Association).filter(
            Association.id == current_user.association_id
        ).first()

        # Genera project_code
        year = datetime.utcnow().year
        count_query = text("""
            SELECT COUNT(*) + 1 as next_num
            FROM agata_projects
            WHERE project_code LIKE :pattern
        """)
        result = db.execute(count_query, {'pattern': f'AGATA-{year}-%'}).fetchone()
        next_num = result.next_num if result else 1
        project_code = f"AGATA-{year}-{next_num:03d}"

        # Crea il progetto in stato 'available' (pronto per assegnazione analyst)
        title = data.get('title') or f"Stella Gaia DR3 {gaia_id}"

        project = Project(
            project_code=project_code,
            title=title,
            gaia_id=str(gaia_id),
            association_id=current_user.association_id,
            state='available'  # Admin lo crea già disponibile
        )
        db.add(project)
        db.flush()

        # Collega assegnazione al progetto
        assignment.project_id = project.id
        db.commit()
        db.refresh(project)

        # Notifica Slack (best-effort)
        try:
            slack_service = get_slack_service()
            slack_service.notify_new_project(db, project, association)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack fallita per progetto {project_code}: {slack_error}")

        return jsonify({
            'success': True,
            'project_id': project.id,
            'project_code': project.project_code,
            'message': f'Creato progetto {project.project_code} - pronto per assegnazione'
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/star-assignments/<int:assignment_id>', methods=['DELETE'])
@login_required
@superuser_required
@audit_action('star_assignment_deleted', 'star_assignment')
def api_delete_star_assignment(assignment_id):
    """
    API: Rimuove un'assegnazione stella.

    Solo superuser può rimuovere assegnazioni.
    Non è possibile rimuovere assegnazioni che hanno già un progetto.

    Returns:
        JSON con success
    """
    db: Session = SessionLocal()
    try:
        assignment = db.query(StarAssignment).filter(
            StarAssignment.id == assignment_id
        ).first()

        if not assignment:
            return jsonify({'error': 'Assegnazione non trovata'}), 404

        if assignment.project_id:
            return jsonify({
                'error': 'Impossibile rimuovere: assegnazione collegata a un progetto'
            }), 400

        gaia_id = assignment.gaia_id
        assoc_name = assignment.association.name

        db.delete(assignment)
        db.commit()

        return jsonify({
            'success': True,
            'message': f'Assegnazione rimossa per stella {gaia_id} da {assoc_name}'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/stars-catalog')
@login_required
@admin_required('analyst')
def api_list_stars():
    """
    API: Lista stelle nel catalogo con filtri.

    Query params:
    - limit: numero risultati (default 100)
    - offset: offset per paginazione
    - search: cerca per Gaia ID

    Returns:
        JSON array di stelle
    """
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    search = request.args.get('search', '')

    db: Session = SessionLocal()
    try:
        is_superuser = current_user.role == 'superuser'
        user_assoc_id = current_user.association_id if not is_superuser else None

        if search:
            query = text("""
                SELECT
                    Source as gaia_id,
                    COUNT(*) as total_points,
                    COUNT(DISTINCT catalogo) as num_catalogs,
                    GROUP_CONCAT(DISTINCT catalogo) as catalogs
                FROM Cataloghi_esterni
                WHERE Source IS NOT NULL AND Source > 0
                  AND CAST(Source AS CHAR) LIKE :search
                  AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
                GROUP BY Source
                ORDER BY total_points DESC
                LIMIT :limit OFFSET :offset
            """)
            result = db.execute(query, {
                'search': f'%{search}%',
                'limit': limit,
                'offset': offset,
                'user_assoc_id': user_assoc_id,
                'is_superuser': 1 if is_superuser else 0
            })
        else:
            query = text("""
                SELECT
                    Source as gaia_id,
                    COUNT(*) as total_points,
                    COUNT(DISTINCT catalogo) as num_catalogs,
                    GROUP_CONCAT(DISTINCT catalogo) as catalogs
                FROM Cataloghi_esterni
                WHERE Source IS NOT NULL AND Source > 0
                  AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
                GROUP BY Source
                ORDER BY total_points DESC
                LIMIT :limit OFFSET :offset
            """)
            result = db.execute(query, {
                'limit': limit,
                'offset': offset,
                'user_assoc_id': user_assoc_id,
                'is_superuser': 1 if is_superuser else 0
            })

        stars = []
        for row in result:
            stars.append({
                'gaia_id': str(row.gaia_id),
                'total_points': row.total_points,
                'num_catalogs': row.num_catalogs,
                'catalogs': row.catalogs.split(',') if row.catalogs else []
            })

        return jsonify(stars)

    finally:
        db.close()


@admin_bp.route('/api/stars-catalog/<gaia_id>/preview-data.arrow')
@login_required
@admin_required('analyst')
def preview_data_arrow(gaia_id):
    """
    Carica dati fotometrici campionati per il minigrafico preview.

    Query params:
    - max_points: numero massimo di punti da caricare (default 1000)

    Restituisce Arrow IPC stream con campi:
    - hjd: float64 - Julian Date
    - mag: float32 - magnitudine
    - catalogo: string - nome catalogo

    Campionamento server-side:
    - Se punti <= 500: carica tutti
    - Se punti 500-5000: carica il 50%
    - Se punti > 5000: carica il 10%
    """
    import pyarrow as pa
    import numpy as np

    db: Session = SessionLocal()
    try:
        is_superuser = current_user.role == 'superuser'
        max_points = request.args.get('max_points', 1000, type=int)

        # Verifica che l'utente possa accedere a questa stella
        check_query = text("""
            SELECT COUNT(*) as cnt FROM Cataloghi_esterni
            WHERE Source = :gaia_id
              AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
        """)
        check_params = {
            'gaia_id': gaia_id,
            'user_assoc_id': current_user.association_id if not is_superuser else None,
            'is_superuser': 1 if is_superuser else 0
        }
        result = db.execute(check_query, check_params).fetchone()
        if not result or result.cnt == 0:
            return jsonify({'error': 'Stella non accessibile'}), 403

        # Carica dati fotometrici con limite e campionamento
        data_query = text("""
            SELECT hjd, Vmag as mag, catalogo
            FROM Cataloghi_esterni
            WHERE Source = :gaia_id
              AND (association_id_owner IS NULL OR association_id_owner = :user_assoc_id OR :is_superuser = 1)
            ORDER BY hjd
        """)

        data_params = {
            'gaia_id': gaia_id,
            'user_assoc_id': current_user.association_id if not is_superuser else None,
            'is_superuser': 1 if is_superuser else 0
        }

        rows = db.execute(data_query, data_params).fetchall()

        if not rows:
            # Ritorna tabella Arrow vuota
            table = pa.table({
                'hjd': pa.array([], type=pa.float64()),
                'mag': pa.array([], type=pa.float32()),
                'catalogo': pa.array([], type=pa.string())
            })
        else:
            # Campionamento server-side intelligente
            total_points = len(rows)

            if total_points <= 500:
                # Carica tutti
                sampling_percent = 100
                sampled_indices = list(range(total_points))
            elif total_points <= 5000:
                # Carica il 50%
                sampling_percent = 50
                step = 2
                sampled_indices = list(range(0, total_points, step))
            else:
                # Carica il 10%
                sampling_percent = 10
                step = max(10, total_points // max_points)
                sampled_indices = list(range(0, total_points, step))

            # Estrai dati campionati
            hjd_data = []
            mag_data = []
            catalog_data = []

            for idx in sampled_indices:
                if idx < total_points:
                    row = rows[idx]
                    hjd_data.append(float(row.hjd))
                    mag_data.append(float(row.mag) if row.mag is not None else 0.0)
                    catalog_data.append(str(row.catalogo))

            # Crea Arrow Table
            table = pa.table({
                'hjd': pa.array(hjd_data, type=pa.float64()),
                'mag': pa.array(mag_data, type=pa.float32()),
                'catalogo': pa.array(catalog_data, type=pa.string())
            })

        # Serializza a IPC stream binario
        sink = pa.BufferOutputStream()
        writer = pa.ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()

        # Ritorna come Response binaria
        from flask import Response
        return Response(
            sink.getvalue().to_pybytes(),
            mimetype='application/octet-stream',
            headers={'Content-Disposition': 'attachment; filename=preview.arrow'}
        )

    finally:
        db.close()
