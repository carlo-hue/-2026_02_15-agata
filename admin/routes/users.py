# agata/admin/routes/users.py
"""
User Management Routes

Gestione utenti:
- Lista utenti con filtri
- Dettaglio utente
- Modifica ruolo (admin/superuser)
- Sospensione/attivazione account
- Storico azioni utente
"""
from flask import render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import Session
from sqlalchemy import and_

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, superuser_required
from agata.admin.services.audit_service import get_user_activity, log_audit
from agata.auth_models import User, Association
from agata.db import SessionLocal


@admin_bp.route('/users')
@login_required
@admin_required('admin')
def list_users():
    """
    Lista utenti con filtri

    Query params:
    - association_id: filtra per associazione
    - role: filtra per ruolo
    - active: filtra attivi/sospesi
    """
    db: Session = SessionLocal()
    try:
        query = db.query(User)

        # Scope (non-superuser vedono solo la propria associazione)
        if current_user.role != 'superuser':
            query = query.filter(User.association_id == current_user.association_id)

        # Filtri
        association_id = request.args.get('association_id', type=int)
        if association_id and current_user.role == 'superuser':
            query = query.filter(User.association_id == association_id)

        role = request.args.get('role')
        if role:
            query = query.filter(User.role == role)

        active = request.args.get('active')
        if active is not None:
            is_active = active.lower() in ['true', '1', 'yes']
            query = query.filter(User.is_active == is_active)

        users = query.order_by(User.name).all()

        # Associations per filtro
        associations = []
        if current_user.role == 'superuser':
            associations = db.query(Association).filter(Association.is_active == True).order_by(Association.name).all()

        return render_template(
            'admin/users/list.html',
            users=users,
            associations=associations,
            is_superuser=current_user.role == 'superuser'
        )

    finally:
        db.close()


@admin_bp.route('/users/<string:user_id>')
@login_required
@admin_required('admin')
def user_detail(user_id):
    """
    Dettaglio utente

    Mostra:
    - Dati base
    - Ruolo e permessi
    - Associazioni di appartenenza
    - Storico azioni (ultimi 30 giorni)
    - Progetti assegnati/reviewati
    """
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            abort(404, "User not found")

        # Check permissions
        if current_user.role != 'superuser':
            if user.association_id != current_user.association_id:
                abort(403, "Access denied to this user")

        # Storico azioni
        activity = get_user_activity(user_id, days=30)

        # Progetti assegnati
        from agata.auth_models import Project
        assigned_projects = db.query(Project).filter(
            Project.assigned_to == user_id,
            Project.state.in_(['assigned', 'in_review'])
        ).all()

        return render_template(
            'admin/users/detail.html',
            user=user,
            activity=activity,
            assigned_projects=assigned_projects,
            can_edit=current_user.role in ['admin', 'superuser'],
            is_superuser=current_user.role == 'superuser'
        )

    finally:
        db.close()


@admin_bp.route('/api/users', methods=['GET'])
@login_required
@admin_required('admin')
def api_list_users():
    """
    API: lista utenti (JSON)
    """
    db: Session = SessionLocal()
    try:
        query = db.query(User)

        if current_user.role != 'superuser':
            query = query.filter(User.association_id == current_user.association_id)

        # === OPTIMIZATION: Eager load association to avoid N lazy loads ===
        from sqlalchemy.orm import joinedload

        users = query.options(
            joinedload(User.association)
        ).order_by(User.name).all()

        return jsonify([
            {
                'id': u.id,
                'email': u.email,
                'name': u.name,
                'surname': u.surname,
                'full_name': u.full_name,
                'role': u.role,
                'is_active': u.is_active,
                'association_id': u.association_id,
                'association_name': u.association.name if u.association else None,  # From eager load
                'last_login': u.last_login.isoformat() if u.last_login else None
            }
            for u in users
        ])

    finally:
        db.close()


@admin_bp.route('/api/users/<string:user_id>/update-role', methods=['POST'])
@login_required
@admin_required('admin')
def api_update_user_role(user_id):
    """
    API: aggiorna ruolo utente

    Superuser: può modificare qualsiasi ruolo
    Admin: può modificare solo analyst/reviewer nella propria associazione
    """
    data = request.json
    if not data or 'role' not in data:
        return jsonify({"error": "Missing role"}), 400

    new_role = data['role']
    valid_roles = ['viewer', 'analyst', 'reviewer', 'admin', 'superuser']
    if new_role not in valid_roles:
        return jsonify({"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}), 400

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Check permissions
        if current_user.role != 'superuser':
            # Admin può modificare solo utenti della propria associazione
            if user.association_id != current_user.association_id:
                return jsonify({"error": "Access denied"}), 403

            # Admin non può creare superuser o altri admin
            if new_role in ['superuser', 'admin']:
                return jsonify({"error": "Insufficient permissions to assign this role"}), 403

        old_role = user.role
        user.role = new_role

        db.commit()
        db.refresh(user)

        # Log audit
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=user.association_id,
            action='user_role_changed',
            entity_type='user',
            entity_id=user.id,
            old_value=old_role,
            new_value=new_role,
            description=f"User {user.email} role changed from {old_role} to {new_role}"
        )

        return jsonify({
            'success': True,
            'user_id': user.id,
            'email': user.email,
            'role': user.role
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/users/<string:user_id>/change-association', methods=['POST'])
@login_required
@superuser_required
def api_change_user_association(user_id):
    """
    API: cambia associazione utente (solo superuser)

    Body JSON:
    - association_id: int - nuova associazione

    Solo superuser può spostare utenti tra associazioni.
    """
    data = request.json
    if not data or 'association_id' not in data:
        return jsonify({"error": "Missing association_id"}), 400

    new_association_id = data['association_id']

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Verifica nuova associazione
        new_association = db.query(Association).filter(
            Association.id == new_association_id
        ).first()
        if not new_association:
            return jsonify({"error": "Association not found"}), 404

        # Non permettere di cambiare associazione a se stesso
        if user.id == current_user.id:
            return jsonify({"error": "Cannot change your own association"}), 400

        old_association_id = user.association_id
        old_association_name = user.association.name if user.association else 'Nessuna'

        user.association_id = new_association_id

        db.commit()
        db.refresh(user)

        # Log audit
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=new_association_id,
            action='user_association_changed',
            entity_type='user',
            entity_id=user.id,
            old_value=old_association_name,
            new_value=new_association.name,
            description=f"User {user.email} moved from '{old_association_name}' to '{new_association.name}'"
        )

        return jsonify({
            'success': True,
            'user_id': user.id,
            'email': user.email,
            'association_id': user.association_id,
            'association_name': new_association.name
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/users/<string:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required('admin')
def api_toggle_user_active(user_id):
    """
    API: attiva/sospendi utente
    """
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Check permissions
        if current_user.role != 'superuser':
            if user.association_id != current_user.association_id:
                return jsonify({"error": "Access denied"}), 403

        # Non permettere di disattivare se stesso
        if user.id == current_user.id:
            return jsonify({"error": "Cannot deactivate yourself"}), 400

        old_status = user.is_active
        user.is_active = not user.is_active

        db.commit()
        db.refresh(user)

        # Log audit
        action = 'user_activated' if user.is_active else 'user_suspended'
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=user.association_id,
            action=action,
            entity_type='user',
            entity_id=user.id,
            old_value=str(old_status),
            new_value=str(user.is_active),
            description=f"User {user.email} {'activated' if user.is_active else 'suspended'}"
        )

        return jsonify({
            'success': True,
            'user_id': user.id,
            'is_active': user.is_active
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/associations-list', methods=['GET'])
@login_required
@superuser_required
def api_list_associations_for_users():
    """
    API: lista associazioni per selezione cambio associazione utente

    Solo superuser.
    """
    db: Session = SessionLocal()
    try:
        associations = db.query(Association).filter(
            Association.is_active == True
        ).order_by(Association.name).all()

        return jsonify([
            {
                'id': a.id,
                'name': a.name,
                'slug': a.slug
            }
            for a in associations
        ])

    finally:
        db.close()
