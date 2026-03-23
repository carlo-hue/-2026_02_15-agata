# agata/admin/routes/projects.py
"""
Project Management Routes

Catalogo progetti AGATA (cuore dell'interfaccia):
- Lista progetti con filtri avanzati
- Dettaglio progetto (vista chiave)
- Azioni su progetti (assegna, riassegna, invia review, cancella)
- Timeline audit trail
- Context Slack
"""
import logging
from flask import render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, audit_action
from agata.admin.services.project_service import (
    assign_project,
    reassign_project,
    send_to_review,
    cancel_project,
    change_project_state,
    self_assign_project
)
from agata.admin.services.audit_service import get_project_audit_trail
from agata.auth_models import Project, User, Association, ProjectSlackThread
from agata.db import SessionLocal


@admin_bp.route('/projects')
@login_required
@admin_required('analyst')
def list_projects():
    """
    Catalogo progetti AGATA con filtri avanzati

    Query params:
    - association_id: filtra per associazione (solo superuser)
    - state: filtra per stato (o 'all' per tutti, 'active' per non-cancellati)
    - gaia_id: cerca per Gaia ID
    - assigned_to: filtra per analyst assegnato ('me' per utente corrente)
    - show: 'mine' (default per analyst), 'all', 'available', 'unassigned'
    - page: paginazione
    """
    db: Session = SessionLocal()
    try:
        is_superuser = current_user.role == 'superuser'
        is_admin = current_user.role == 'admin'
        is_analyst = current_user.role in ['analyst', 'reviewer']

        # Base query
        query = db.query(Project)

        # Scope per associazione (non-superuser vedono solo la propria)
        if not is_superuser:
            query = query.filter(Project.association_id == current_user.association_id)

        # Filtro associazione (solo superuser)
        association_id = request.args.get('association_id', type=int)
        if association_id and is_superuser:
            query = query.filter(Project.association_id == association_id)

        # Filtro "show" - determina vista predefinita
        # Default: tutti vedono "mine" (i loro progetti)
        show = request.args.get('show')
        if show is None:
            # Default per tutti: i propri progetti
            show = 'mine'

        # Applica filtro "show"
        if show == 'mine':
            # Solo progetti assegnati a me
            query = query.filter(Project.assigned_to == current_user.id)
        elif show == 'available':
            # Solo progetti disponibili per assegnazione (not assigned e in available/incoming state)
            query = query.filter(
                Project.state.in_(['available', 'incoming']),
                Project.assigned_to == None
            )
        elif show == 'unassigned':
            # Progetti senza analyst assegnato (incoming, available), non cancellati
            query = query.filter(
                Project.assigned_to == None,
                Project.state != 'cancelled'
            )
        elif show == 'active':
            # Tutti i progetti non cancellati
            query = query.filter(Project.state != 'cancelled')
        # 'all' = nessun filtro aggiuntivo

        # Filtro stato specifico (sovrascrive "show" se presente)
        state = request.args.get('state')
        if state and state != 'all':
            if state == 'active':
                query = query.filter(Project.state != 'cancelled')
            else:
                query = query.filter(Project.state == state)

        # Cerca per Gaia ID
        gaia_id = request.args.get('gaia_id')
        if gaia_id:
            query = query.filter(Project.gaia_id.like(f'%{gaia_id}%'))

        # Filtro analyst assegnato
        assigned_to = request.args.get('assigned_to')
        if assigned_to:
            if assigned_to == 'me':
                query = query.filter(Project.assigned_to == current_user.id)
            elif assigned_to == 'none':
                query = query.filter(Project.assigned_to == None)
            else:
                query = query.filter(Project.assigned_to == assigned_to)

        # Ordinamento
        sort_by = request.args.get('sort', 'updated_at')
        sort_order = request.args.get('order', 'desc')

        # Mapping dei campi ordinabili
        sortable_fields = {
            'project_code': Project.project_code,
            'gaia_id': Project.gaia_id,
            'state': Project.state,
            'updated_at': Project.updated_at,
            'created_at': Project.created_at,
        }

        # Validazione del campo di ordinamento
        if sort_by not in sortable_fields:
            sort_by = 'updated_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'

        # Applica ordinamento
        order_column = sortable_fields[sort_by]
        if sort_order == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginazione
        page = request.args.get('page', 1, type=int)
        per_page = 50
        total = query.count()

        # === OPTIMIZATION: Eager load relationships to avoid N+1 queries ===
        from sqlalchemy.orm import joinedload

        projects = query.options(
            joinedload(Project.association),
            joinedload(Project.assigned_user),
            joinedload(Project.reviewer)
        ).limit(per_page).offset((page - 1) * per_page).all()

        # === OPTIMIZATION: Batch load slack threads data ===
        project_ids = [p.id for p in projects]
        slack_threads_data = db.query(ProjectSlackThread).filter(
            ProjectSlackThread.project_id.in_(project_ids),
            ProjectSlackThread.is_active == True
        ).all()

        # Build dict for O(1) lookup
        slack_map = {}
        for st in slack_threads_data:
            if st.project_id not in slack_map:
                slack_map[st.project_id] = st

        # Arricchisci con dati (tutto da cache, nessuna query!)
        result = []
        for p in projects:
            slack_thread = slack_map.get(p.id)

            result.append({
                'id': p.id,
                'project_code': p.project_code,
                'gaia_id': p.gaia_id,
                'title': p.title,
                'state': p.state,
                'association_name': p.association.name if p.association else None,  # From eager load
                'assigned_user_name': p.assigned_user.full_name if p.assigned_user else None,  # From eager load
                'assigned_user_id': str(p.assigned_to) if p.assigned_to else None,
                'reviewer_name': p.reviewer.full_name if p.reviewer else None,  # From eager load
                'notes': p.notes,
                'slack_channel_id': slack_thread.channel_id if slack_thread else None,
                'slack_thread_ts': slack_thread.thread_ts if slack_thread else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            })

        # === OPTIMIZATION: Get associations with LIMIT to avoid loading all ===
        associations = []
        if is_superuser:
            associations = db.query(Association).filter(
                Association.is_active == True
            ).order_by(Association.name).limit(100).all()  # Limit for dropdown

        # === OPTIMIZATION: Eager load user associations ===
        analysts = []
        if is_admin or is_superuser:
            analyst_query = db.query(User).options(
                joinedload(User.association)  # Avoid lazy load
            ).filter(
                User.is_active == True,
                User.role.in_(['analyst', 'reviewer', 'admin'])
            )
            if not is_superuser:
                analyst_query = analyst_query.filter(User.association_id == current_user.association_id)
            analysts = analyst_query.order_by(User.name).all()

        # === OPTIMIZATION: Aggregate counts in single query instead of 2 separate count() calls ===
        from sqlalchemy import case, func

        count_results = db.query(
            func.sum(
                case(
                    (
                        (Project.assigned_to == current_user.id) &
                        (Project.state != 'cancelled'),
                        1
                    ),
                    else_=0
                )
            ).label('my_projects_count'),
            func.sum(
                case(
                    (
                        (Project.state.in_(['available', 'incoming'])) &
                        (Project.assigned_to == None),
                        1
                    ),
                    else_=0
                )
            ).label('available_count')
        )

        if not is_superuser:
            count_results = count_results.filter(Project.association_id == current_user.association_id)

        counts = count_results.first()
        my_projects_count = counts.my_projects_count or 0
        available_count = counts.available_count or 0

        return render_template(
            'admin/projects/list.html',
            projects=result,
            associations=associations,
            analysts=analysts,
            total=total,
            page=page,
            per_page=per_page,
            is_superuser=is_superuser,
            is_admin=is_admin,
            current_show=show,
            current_state=state,
            current_assigned_to=assigned_to,
            current_gaia_id=gaia_id,
            current_association_id=association_id,
            my_projects_count=my_projects_count,
            available_count=available_count,
            current_sort=sort_by,
            current_order=sort_order
        )

    finally:
        db.close()


@admin_bp.route('/projects/<int:project_id>')
@login_required
@admin_required('analyst')
def project_detail(project_id):
    """
    Vista dettaglio progetto (schermata chiave)

    Mostra:
    - Intestazione (project_code, gaia_id, stato)
    - Azioni context-aware (bottoni per stato attuale)
    - Sezione Slack (thread/canale, link)
    - Dati scientifici
    - Timeline audit trail completa
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            abort(404, "Project not found")

        # Check permissions (non-superuser solo la propria associazione)
        if current_user.role != 'superuser':
            if project.association_id != current_user.association_id:
                abort(403, "Access denied to this project")

        # Slack thread info
        slack_thread = db.query(ProjectSlackThread).filter(
            ProjectSlackThread.project_id == project_id,
            ProjectSlackThread.is_active == True
        ).first()

        # Audit trail
        audit_trail = get_project_audit_trail(project_id)

        # Azioni permesse (context-aware per stato)
        allowed_actions = get_allowed_actions(project, current_user)

        # Analysts disponibili per assegnazione (stessa associazione)
        available_analysts = db.query(User).filter(
            and_(
                User.association_id == project.association_id,
                User.is_active == True,
                User.role.in_(['analyst', 'reviewer', 'admin'])
            )
        ).order_by(User.name).all()

        return render_template(
            'admin/projects/detail.html',
            project=project,
            slack_thread=slack_thread,
            audit_trail=audit_trail,
            allowed_actions=allowed_actions,
            available_analysts=available_analysts
        )

    finally:
        db.close()


def get_allowed_actions(project: Project, user: User) -> dict:
    """
    Determina azioni permesse per progetto in base a stato e ruolo utente

    Returns:
        Dict con flag booleani per ogni azione
    """
    state = project.state
    role = user.role

    # Admin e superuser possono tutto
    is_admin = role in ['admin', 'superuser']

    # Analyst può auto-assegnarsi progetti available della propria associazione
    can_self_assign = (
        state == 'available' and
        role in ['analyst', 'reviewer', 'admin'] and
        user.association_id == project.association_id
    )

    return {
        'can_assign': state == 'available' and is_admin,
        'can_self_assign': can_self_assign,
        'can_reassign': state in ['assigned', 'in_review'] and is_admin,
        'can_send_to_review': state == 'assigned' and (is_admin or user.id == project.assigned_to),
        'can_cancel': state not in ['cancelled', 'accepted_aavso'] and is_admin,
        'can_change_state': is_admin,
        'can_edit': is_admin,
        'can_open_editor': state in ['assigned', 'in_review'] and (is_admin or user.id == project.assigned_to)
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@admin_bp.route('/api/projects/<int:project_id>/assignable-users', methods=['GET'])
@login_required
@admin_required('admin')
def api_get_assignable_users(project_id):
    """
    API: ottiene lista utenti assegnabili a un progetto

    Restituisce utenti con ruolo analyst/reviewer/admin
    della stessa associazione del progetto.
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({'error': 'Progetto non trovato'}), 404

        # Verifica permessi: solo admin/superuser della stessa associazione
        if current_user.role != 'superuser':
            if current_user.association_id != project.association_id:
                return jsonify({'error': 'Non autorizzato'}), 403

        # Utenti assegnabili: analyst, reviewer, admin della stessa associazione
        assignable_roles = ['analyst', 'reviewer', 'admin']
        users = db.query(User).filter(
            User.association_id == project.association_id,
            User.role.in_(assignable_roles),
            User.is_active == True
        ).order_by(User.name).all()

        return jsonify([
            {
                'id': u.id,
                'name': u.full_name or u.name or u.email,
                'email': u.email,
                'role': u.role
            }
            for u in users
        ])

    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/assign', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_assigned', 'project')
def api_assign_project(project_id):
    """
    API: assegna progetto ad analyst
    """
    data = request.json
    if not data or 'analyst_id' not in data:
        return jsonify({"error": "Missing analyst_id"}), 400

    success, error, project = assign_project(
        project_id=project_id,
        analyst_user_id=data['analyst_id'],
        assigned_by_user_id=current_user.id
    )

    if not success:
        return jsonify({"error": error}), 400

    return jsonify({
        'success': True,
        'project_id': project.id,
        'project_code': project.project_code,
        'state': project.state,
        'assigned_to': project.assigned_to
    })


@admin_bp.route('/api/projects/<int:project_id>/self-assign', methods=['POST'])
@login_required
@admin_required('analyst')
@audit_action('project_self_assigned', 'project')
def api_self_assign_project(project_id):
    """
    API: auto-assegnazione progetto da parte dell'analyst

    L'analyst può assegnarsi un progetto in stato 'available'
    della propria associazione.
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({"error": "Progetto non trovato"}), 404

        # Verifica che l'utente appartenga alla stessa associazione
        if current_user.association_id != project.association_id:
            return jsonify({"error": "Non autorizzato per questa associazione"}), 403

        success, error, project = self_assign_project(
            project_id=project_id,
            analyst_user_id=current_user.id
        )

        if not success:
            return jsonify({"error": error}), 400

        return jsonify({
            'success': True,
            'project_id': project.id,
            'project_code': project.project_code,
            'state': project.state,
            'assigned_to': str(project.assigned_to),
            'message': f'Progetto {project.project_code} assegnato con successo'
        })

    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/reassign', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_reassigned', 'project')
def api_reassign_project(project_id):
    """
    API: riassegna progetto ad altro analyst
    """
    data = request.json
    if not data or 'analyst_id' not in data:
        return jsonify({"error": "Missing analyst_id"}), 400

    success, error, project = reassign_project(
        project_id=project_id,
        new_analyst_user_id=data['analyst_id'],
        reassigned_by_user_id=current_user.id,
        reason=data.get('reason')
    )

    if not success:
        return jsonify({"error": error}), 400

    return jsonify({
        'success': True,
        'project_id': project.id,
        'state': project.state,
        'assigned_to': project.assigned_to
    })


@admin_bp.route('/api/projects/<int:project_id>/send-to-review', methods=['POST'])
@login_required
@admin_required('analyst')
@audit_action('project_sent_to_review', 'project')
def api_send_to_review(project_id):
    """
    API: invia progetto in review

    Permesso: analyst assegnato, reviewer, admin, superuser
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Check permissions
        if current_user.role not in ['admin', 'superuser', 'reviewer']:
            # Analyst può inviare solo se è assegnato
            if project.assigned_to != current_user.id:
                return jsonify({"error": "Only assigned analyst can send to review"}), 403

        success, error, project = send_to_review(
            project_id=project_id,
            sent_by_user_id=current_user.id
        )

        if not success:
            return jsonify({"error": error}), 400

        return jsonify({
            'success': True,
            'project_id': project.id,
            'state': project.state
        })

    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/cancel', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_cancelled', 'project')
def api_cancel_project(project_id):
    """
    API: cancella progetto (richiede motivazione)
    """
    data = request.json
    if not data or 'reason' not in data or not data['reason'].strip():
        return jsonify({"error": "Cancellation reason is required"}), 400

    success, error, project = cancel_project(
        project_id=project_id,
        cancelled_by_user_id=current_user.id,
        reason=data['reason']
    )

    if not success:
        return jsonify({"error": error}), 400

    return jsonify({
        'success': True,
        'project_id': project.id,
        'state': project.state,
        'cancelled_at': project.cancelled_at.isoformat() if project.cancelled_at else None
    })


@admin_bp.route('/api/projects/<int:project_id>/change-state', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_state_changed', 'project')
def api_change_project_state(project_id):
    """
    API: cambia stato progetto manualmente

    Solo per admin/superuser in casi eccezionali
    """
    data = request.json
    if not data or 'new_state' not in data:
        return jsonify({"error": "Missing new_state"}), 400

    success, error, project = change_project_state(
        project_id=project_id,
        new_state=data['new_state'],
        user_id=current_user.id,
        reason=data.get('reason')
    )

    if not success:
        return jsonify({"error": error}), 400

    return jsonify({
        'success': True,
        'project_id': project.id,
        'state': project.state
    })


@admin_bp.route('/api/projects/<int:project_id>/make-available', methods=['POST'])
@login_required
@admin_required('admin')
@audit_action('project_made_available', 'project')
def api_make_project_available(project_id):
    """
    API: Promuove un progetto da 'incoming' a 'available'.

    Workflow:
    - Superuser carica stella e crea progetto in stato 'incoming'
    - Admin dell'associazione lo vede e decide di renderlo disponibile
    - Il progetto passa a 'available' e diventa assegnabile agli analyst

    Solo admin dell'associazione proprietaria può farlo.
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({"error": "Progetto non trovato"}), 404

        # Verifica permessi: deve essere admin della stessa associazione
        if current_user.role != 'superuser':
            if current_user.association_id != project.association_id:
                return jsonify({"error": "Non puoi gestire progetti di altre associazioni"}), 403

        # Verifica stato
        if project.state != 'incoming':
            return jsonify({
                "error": f"Il progetto è in stato '{project.state}', non 'incoming'"
            }), 400

        # Promuovi a available
        project.state = 'available'
        db.commit()

        return jsonify({
            'success': True,
            'project_id': project.id,
            'project_code': project.project_code,
            'state': project.state,
            'message': f'Progetto {project.project_code} ora disponibile per assegnazione'
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/audit-trail', methods=['GET'])
@login_required
@admin_required('analyst')
def api_project_audit_trail(project_id):
    """
    API: audit trail completo progetto
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Check permissions
        if current_user.role != 'superuser':
            if project.association_id != current_user.association_id:
                return jsonify({"error": "Access denied"}), 403

        audit_trail = get_project_audit_trail(project_id)

        return jsonify([
            {
                'id': a.id,
                'user_email': a.user_email,
                'action': a.action,
                'old_value': a.old_value,
                'new_value': a.new_value,
                'description': a.description,
                'created_at': a.created_at.isoformat() if a.created_at else None
            }
            for a in audit_trail
        ])

    finally:
        db.close()


@admin_bp.route('/api/projects', methods=['POST'])
@login_required
@admin_required('admin')
def create_project():
    """
    API: Crea nuovo progetto
    
    Body:
    - gaia_id: ID Gaia DR3 (required)
    - association_id: ID associazione (required per superuser, auto per admin)
    - title: Titolo progetto (optional)
    - source: Sorgente dati (optional)
    - ra: Right Ascension (optional)
    - dec_deg: Declination (optional)
    - magnitude: Magnitudine (optional)
    """
    db: Session = SessionLocal()
    try:
        data = request.get_json()
        
        # Validate required fields
        gaia_id = data.get('gaia_id')
        if not gaia_id:
            return jsonify({'error': 'gaia_id is required'}), 400
            
        # Check if project with same Gaia ID already exists
        existing = db.query(Project).filter(Project.gaia_id == gaia_id).first()
        if existing:
            return jsonify({'error': f'Project with Gaia ID {gaia_id} already exists (Project Code: {existing.project_code})'}), 409
        
        # Determine association
        if current_user.role == 'superuser':
            association_id = data.get('association_id')
            if not association_id:
                return jsonify({'error': 'association_id is required for superuser'}), 400
        else:
            # Admin can only create projects for their own association
            association_id = current_user.association_id
            
        # Verify association exists
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({'error': 'Association not found'}), 404
            
        # Generate project code (format: AGATA-YYYY-NNN)
        from datetime import datetime
        year = datetime.now().year
        
        # Find last project code for this year
        last_project = db.query(Project).filter(
            Project.project_code.like(f'AGATA-{year}-%')
        ).order_by(Project.project_code.desc()).first()
        
        if last_project:
            # Extract number and increment
            try:
                last_num = int(last_project.project_code.split('-')[-1])
                next_num = last_num + 1
            except:
                next_num = 1
        else:
            next_num = 1
            
        project_code = f'AGATA-{year}-{next_num:03d}'

        # Determina stato iniziale:
        # - Superuser crea in 'incoming' (admin deve promuovere)
        # - Admin crea direttamente in 'available'
        initial_state = 'incoming' if current_user.role == 'superuser' else 'available'

        # Auto-fetch coordinate e parametri stellari da Gaia se non forniti
        ra = float(data['ra']) if data.get('ra') else None
        dec_deg = float(data['dec_deg']) if data.get('dec_deg') else None
        magnitude = float(data['magnitude']) if data.get('magnitude') else None

        if ra is None or dec_deg is None or magnitude is None:
            from agata.admin.routes.catalogs.common import resolve_gaia_coordinates
            logger.info(f"Auto-fetching coordinates for Gaia ID: {gaia_id}")
            gaia_info = resolve_gaia_coordinates(gaia_id)

            if gaia_info:
                ra = ra or gaia_info.get('ra')
                dec_deg = dec_deg or gaia_info.get('dec')
                magnitude = magnitude or gaia_info.get('phot_g_mean_mag')
                logger.info(f"Auto-fetched: RA={ra}, Dec={dec_deg}, Mag={magnitude}")
            else:
                logger.warning(f"Could not auto-fetch Gaia data for {gaia_id}")

        # Create project
        project = Project(
            project_code=project_code,
            gaia_id=gaia_id,
            association_id=association_id,
            title=data.get('title'),
            source=data.get('source'),
            ra=ra,
            dec_deg=dec_deg,
            magnitude=magnitude,
            state=initial_state
        )
        
        db.add(project)
        db.flush()
        
        # Log audit
        from agata.auth_models import AuditLog
        audit = AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=current_user.association_id,
            action='project_created',
            entity_type='project',
            entity_id=str(project.id),
            new_value=project_code,
            description=f'Progetto {project_code} creato manualmente via interfaccia admin',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            outcome='success'
        )
        db.add(audit)
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Progetto creato con successo',
            'project_id': project.id,
            'project_code': project.project_code,
            'ra': ra,
            'dec': dec_deg,
            'magnitude': magnitude
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/refresh-gaia-data', methods=['POST'])
@login_required
@admin_required('analyst')
def refresh_gaia_data(project_id: int):
    """
    POST /api/projects/<id>/refresh-gaia-data

    Auto-fetch e aggiorna coordinate + parametri stellari da Gaia DR3.
    Utile per progetti creati senza coordinate o per aggiornare dati obsoleti.

    Returns:
        JSON con coordinate aggiornate
    """
    db: Session = SessionLocal()
    try:
        # Fetch project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({'error': 'Project not found'}), 404

        # Check permissions
        if current_user.role not in ['superuser', 'admin']:
            if project.association_id != current_user.association_id:
                return jsonify({'error': 'Unauthorized'}), 403

        if not project.gaia_id:
            return jsonify({'error': 'Project must have gaia_id'}), 400

        # Fetch da Gaia
        from agata.admin.routes.catalogs.common import resolve_gaia_coordinates
        logger.info(f"Refreshing Gaia data for project {project_id}, Gaia ID: {project.gaia_id}")
        gaia_info = resolve_gaia_coordinates(project.gaia_id)

        if not gaia_info:
            return jsonify({'error': f'Could not fetch Gaia data for {project.gaia_id}'}), 404

        # Aggiorna campi
        old_values = {
            'ra': project.ra,
            'dec': project.dec_deg,
            'magnitude': project.magnitude
        }

        project.ra = gaia_info.get('ra')
        project.dec_deg = gaia_info.get('dec')
        project.magnitude = gaia_info.get('phot_g_mean_mag')

        # Log audit
        from agata.auth_models import AuditLog
        audit = AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=current_user.association_id,
            action='project_gaia_refresh',
            entity_type='project',
            entity_id=str(project.id),
            old_value=str(old_values),
            new_value=str(gaia_info),
            description=f'Auto-refresh dati Gaia per progetto {project.project_code}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            outcome='success'
        )
        db.add(audit)

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Dati Gaia aggiornati con successo',
            'project_id': project_id,
            'gaia_id': project.gaia_id,
            'updated_data': {
                'ra': project.ra,
                'dec': project.dec_deg,
                'magnitude': project.magnitude,
                'bp_rp': gaia_info.get('bp_rp'),
                'teff': gaia_info.get('teff')
            },
            'previous_data': old_values
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error refreshing Gaia data: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/notes', methods=['PUT'])
@login_required
@admin_required('analyst')
@audit_action('project_notes_updated', 'project')
def api_update_project_notes(project_id):
    """
    API: Aggiorna le note di un progetto.

    Permessi:
    - Analyst assegnato al progetto
    - Admin/Superuser della stessa associazione

    Body JSON:
    - notes: str (può essere vuoto per cancellare)

    Returns:
        JSON con success e notes aggiornate
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({'error': 'Progetto non trovato'}), 404

        # Verifica permessi
        if current_user.role != 'superuser':
            if current_user.association_id != project.association_id:
                return jsonify({'error': 'Non autorizzato'}), 403
            # Analyst può modificare solo se assegnato
            if current_user.role == 'analyst' and project.assigned_to != current_user.id:
                return jsonify({'error': 'Solo l\'analyst assegnato può modificare le note'}), 403

        data = request.get_json() or {}
        notes = data.get('notes', '').strip()

        # Aggiorna notes (può essere vuoto)
        project.notes = notes if notes else None
        db.commit()

        return jsonify({
            'success': True,
            'project_id': project.id,
            'notes': project.notes,
            'message': 'Note aggiornate'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/projects/<int:project_id>/move', methods=['POST'])
@login_required
@admin_required('superuser')
@audit_action('project_moved', 'project')
def api_move_project(project_id):
    """
    API: Sposta progetto ad un'altra associazione (solo superuser)

    Permette di riassegnare un progetto da un'associazione all'altra.
    Verifica che l'associazione di destinazione non abbia già un progetto
    attivo per la stessa stella (gaia_id).

    Body:
    - new_association_id: ID della nuova associazione (required)

    Returns:
        JSON con success, project_id, new_association_name
    """
    db: Session = SessionLocal()
    try:
        data = request.get_json()
        if not data or 'new_association_id' not in data:
            return jsonify({'error': 'new_association_id è obbligatorio'}), 400

        new_association_id = data['new_association_id']

        # Recupera il progetto
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return jsonify({'error': 'Progetto non trovato'}), 404

        # Verifica che non sia cancellato
        if project.state == 'cancelled':
            return jsonify({'error': 'Non è possibile spostare un progetto cancellato'}), 400

        # Verifica che la nuova associazione sia diversa
        if project.association_id == new_association_id:
            return jsonify({'error': 'Il progetto appartiene già a questa associazione'}), 400

        # Verifica che la nuova associazione esista e sia attiva
        new_association = db.query(Association).filter(
            Association.id == new_association_id,
            Association.is_active == True
        ).first()
        if not new_association:
            return jsonify({'error': 'Associazione di destinazione non trovata o non attiva'}), 404

        # Verifica che l'associazione di destinazione non abbia già un progetto
        # attivo per la stessa stella
        existing_project = db.query(Project).filter(
            Project.gaia_id == project.gaia_id,
            Project.association_id == new_association_id,
            Project.state != 'cancelled'
        ).first()

        if existing_project:
            return jsonify({
                'error': f"L'associazione {new_association.name} ha già un progetto attivo "
                         f"per questa stella ({existing_project.project_code})"
            }), 400

        # Memorizza vecchia associazione per audit
        old_association = project.association
        old_association_name = old_association.name if old_association else 'N/A'

        # Sposta il progetto
        project.association_id = new_association_id

        # Se il progetto è assegnato, rimuovi l'assegnazione
        # (l'analista appartiene all'associazione precedente)
        if project.assigned_to:
            project.assigned_to = None
            project.assigned_at = None
            # Se era in stato 'assigned', torna a 'available'
            if project.state == 'assigned':
                project.state = 'available'

        db.commit()

        return jsonify({
            'success': True,
            'project_id': project.id,
            'project_code': project.project_code,
            'old_association_name': old_association_name,
            'new_association_name': new_association.name,
            'state': project.state,
            'message': f'Progetto spostato da {old_association_name} a {new_association.name}'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()
