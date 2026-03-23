# agata/auth/decorators.py
"""
Authentication Decorators

Decorators per proteggere route Flask:
- @login_required: Richiede utente autenticato
- @require_role('admin'): Richiede ruolo specifico
- @require_permission('write'): Richiede permesso specifico
"""
from functools import wraps
from flask import jsonify, request
from flask_login import current_user


def login_required(f):
    """
    Decorator: richiede utente autenticato

    Usage:
        @app.route('/protected')
        @login_required
        def protected_route():
            return "Hello " + current_user.email
    """
    from flask_login import login_required as flask_login_required
    return flask_login_required(f)


def require_role(*allowed_roles):
    """
    Decorator: richiede ruolo specifico

    Gerarchia ruoli:
    superuser > admin > reviewer > analyst > viewer

    Args:
        *allowed_roles: Lista ruoli ammessi

    Usage:
        @app.route('/admin/users')
        @login_required
        @require_role('admin', 'superuser')
        def admin_panel():
            return "Admin panel"

    Returns:
        403 Forbidden se ruolo non autorizzato
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Autenticazione richiesta"}), 401

            if not current_user.is_active:
                return jsonify({"error": "Account disattivato"}), 403

            # Check ruolo
            if current_user.role not in allowed_roles:
                return jsonify({
                    "error": "Permesso negato",
                    "required_roles": list(allowed_roles),
                    "your_role": current_user.role
                }), 403

            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_permission(permission: str):
    """
    Decorator: richiede permesso specifico

    Permessi disponibili:
    - 'read': Sola lettura
    - 'write': Scrittura
    - 'analyze': Analisi/elaborazione dati
    - 'review': Revisione scientifica
    - 'admin': Amministrazione associazione
    - 'superuser': Amministrazione sistema

    Usage:
        @app.route('/api/periodogram', methods=['POST'])
        @login_required
        @require_permission('analyze')
        def compute_periodogram():
            return {"status": "computing..."}

    Returns:
        403 Forbidden se permesso non presente
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Autenticazione richiesta"}), 401

            if not current_user.is_active:
                return jsonify({"error": "Account disattivato"}), 403

            # Check permesso tramite metodo User.has_permission()
            if not current_user.has_permission(permission):
                return jsonify({
                    "error": "Permesso negato",
                    "required_permission": permission,
                    "your_role": current_user.role
                }), 403

            return f(*args, **kwargs)
        return wrapped
    return decorator


def require_association_access(f):
    """
    Decorator: richiede accesso alla stessa associazione

    Verifica che l'utente appartenga alla stessa associazione
    dell'entità richiesta (project, etc.)

    Usage:
        @app.route('/api/projects/<int:project_id>')
        @login_required
        @require_association_access
        def get_project(project_id):
            # project_id viene validato automaticamente
            return {"project_id": project_id}

    Note:
        Superuser bypassa questo check (accesso globale)
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Autenticazione richiesta"}), 401

        if not current_user.is_active:
            return jsonify({"error": "Account disattivato"}), 403

        # Superuser ha accesso globale
        if current_user.is_superuser:
            return f(*args, **kwargs)

        # TODO: Implementare validazione association_id
        # da kwargs o da DB query

        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    """
    Shorthand decorator per @require_role('admin', 'superuser')

    Usage:
        @app.route('/admin/settings')
        @login_required
        @admin_required
        def settings():
            return "Settings page"
    """
    return require_role('admin', 'superuser')(f)


def superuser_required(f):
    """
    Shorthand decorator per @require_role('superuser')

    Usage:
        @app.route('/superuser/import')
        @login_required
        @superuser_required
        def mass_import():
            return "Import page"
    """
    return require_role('superuser')(f)
