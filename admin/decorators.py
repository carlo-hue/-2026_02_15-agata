# agata/admin/decorators.py
"""
Admin Decorators - RBAC e permission checking

Sistema di permessi per associazione:
- Superuser: accesso globale
- Admin: gestione associazione propria
- Reviewer/Analyst: accesso limitato alla propria associazione
- Viewer: sola lettura

I permessi sono context-aware: un admin può gestire solo la propria associazione,
non altre associazioni.
"""
from functools import wraps
from flask import abort, request, jsonify, current_app
from flask_login import current_user


def admin_required(min_role='admin'):
    """
    Decorator: richiede ruolo admin o superiore

    Args:
        min_role: ruolo minimo richiesto ('viewer', 'analyst', 'reviewer', 'admin', 'superuser')

    Usage:
        @admin_required('superuser')  # Solo superuser
        @admin_required('admin')      # Admin o superuser
        @admin_required('reviewer')   # Reviewer, admin o superuser
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({"error": "Authentication required"}), 401
                abort(401)

            # Gerarchia ruoli
            role_hierarchy = {
                'viewer': 0,
                'analyst': 1,
                'reviewer': 2,
                'admin': 3,
                'superuser': 4
            }

            user_level = role_hierarchy.get(current_user.role, -1)
            required_level = role_hierarchy.get(min_role, 99)

            if user_level < required_level:
                current_app.logger.warning(
                    f"Access denied: user {current_user.email} (role={current_user.role}) "
                    f"attempted to access {request.path} (requires {min_role})"
                )
                if request.is_json:
                    return jsonify({"error": "Insufficient permissions"}), 403
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def superuser_required(f):
    """
    Decorator: solo superuser
    Shortcut per admin_required('superuser')
    """
    return admin_required('superuser')(f)


def can_manage_association(association_id: int) -> bool:
    """
    Verifica se l'utente corrente può gestire un'associazione

    Rules:
    - Superuser: può gestire tutte le associazioni
    - Admin: può gestire solo la propria associazione
    - Altri: non possono gestire associazioni

    Args:
        association_id: ID associazione da verificare

    Returns:
        True se l'utente può gestire l'associazione
    """
    if not current_user.is_authenticated:
        return False

    # Superuser può tutto
    if current_user.role == 'superuser':
        return True

    # Admin può gestire solo la propria associazione
    if current_user.role == 'admin':
        return current_user.association_id == association_id

    # Altri ruoli non possono gestire associazioni
    return False


def can_view_association(association_id: int) -> bool:
    """
    Verifica se l'utente può visualizzare dati di un'associazione

    Rules:
    - Superuser: può vedere tutto
    - Altri: solo la propria associazione

    Args:
        association_id: ID associazione

    Returns:
        True se può visualizzare
    """
    if not current_user.is_authenticated:
        return False

    if current_user.role == 'superuser':
        return True

    return current_user.association_id == association_id


def association_scope_required(f):
    """
    Decorator: verifica che l'utente possa accedere all'associazione specificata

    Expects:
        - association_id in URL parameters OR
        - association_id in JSON body

    Usage:
        @admin_bp.route('/associations/<int:association_id>/users')
        @association_scope_required
        def list_association_users(association_id):
            # association_id già validato
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)

        # Estrai association_id da kwargs (URL params) o request body
        association_id = kwargs.get('association_id')
        if association_id is None and request.is_json:
            association_id = request.json.get('association_id')

        if association_id is None:
            current_app.logger.error(f"association_scope_required: no association_id provided for {request.path}")
            abort(400, "Missing association_id")

        # Superuser bypassa check
        if current_user.role == 'superuser':
            return f(*args, **kwargs)

        # Altri utenti: solo la propria associazione
        if current_user.association_id != association_id:
            current_app.logger.warning(
                f"Access denied: user {current_user.email} (association={current_user.association_id}) "
                f"attempted to access association {association_id}"
            )
            abort(403, "Access denied to this association")

        return f(*args, **kwargs)
    return decorated_function


def audit_action(action: str, entity_type: str = None):
    """
    Decorator: registra azione in audit log

    Args:
        action: tipo azione (es: 'project_state_changed', 'user_updated')
        entity_type: tipo entità (es: 'project', 'user', 'association')

    Usage:
        @audit_action('project_assigned', 'project')
        def assign_project(project_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Esegui funzione
            result = f(*args, **kwargs)

            # Log audit (in background, non bloccare risposta)
            try:
                from agata.admin.services.audit_service import log_audit

                entity_id = kwargs.get('id') or kwargs.get('project_id') or kwargs.get('user_id')

                log_audit(
                    user_id=current_user.id if current_user.is_authenticated else None,
                    user_email=current_user.email if current_user.is_authenticated else None,
                    association_id=current_user.association_id if current_user.is_authenticated else None,
                    action=action,
                    entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id else None,
                    description=f"{action} on {entity_type} {entity_id}",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
            except Exception as e:
                current_app.logger.error(f"Failed to log audit: {e}")

            return result
        return decorated_function
    return decorator
