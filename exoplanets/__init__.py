"""
exoplanets - Modulo Analisi Esopianeti

Endpoint:
- /agata/exoplanets/
- /agata/exoplanets/api/bls
- /agata/exoplanets/api/transit-fit
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

# Blueprint esopianeti
exoplanets_bp = Blueprint(
    'exoplanets',
    __name__,
    template_folder='../templates/exoplanets',
    static_folder='../static'
)


# ============================================================================
# PROTEZIONE GLOBALE BLUEPRINT
# ============================================================================

@exoplanets_bp.before_request
def require_analyst_role():
    """
    Protezione globale per tutto il blueprint exoplanets.

    Richiede ruolo minimo: analyst
    Ruoli ammessi: analyst, reviewer, admin, superuser
    Blocca: viewer e utenti non autenticati
    """
    # Permetti accesso a file statici senza autenticazione
    if request.endpoint and 'static' in request.endpoint:
        return None

    # Verifica autenticazione
    if not current_user.is_authenticated:
        return _render_access_denied(
            title="Autenticazione Richiesta",
            message="Per accedere all'applicazione <strong>Esopianeti</strong> devi effettuare il login.",
            action_url="/auth/login/google",
            action_text="Login con Google"
        ), 401

    # Verifica account attivo
    if not current_user.is_active:
        return _render_access_denied(
            title="Account Disattivato",
            message="Il tuo account è stato disattivato. Contatta l'amministratore per maggiori informazioni.",
            show_user_info=True
        ), 403

    # Verifica ruolo minimo (analyst o superiore)
    allowed_roles = ['analyst', 'reviewer', 'admin', 'superuser']
    if current_user.role not in allowed_roles:
        return _render_access_denied(
            title="Accesso Negato",
            message=f"L'accesso a <strong>Esopianeti</strong> è riservato agli analisti.<br><br>"
                    f"Il tuo ruolo attuale è: <span style='color: #e74c3c'><strong>{current_user.role}</strong></span>",
            details=f"Ruoli ammessi: <strong>{', '.join(allowed_roles)}</strong>",
            show_user_info=True,
            action_url="/",
            action_text="Torna alla Home"
        ), 403

    # Utente autorizzato, procedi
    return None


def _render_access_denied(title, message, details=None, action_url=None, action_text=None, show_user_info=False):
    """
    Renderizza pagina HTML di errore accesso negato
    """
    user_info = ""
    if show_user_info and current_user.is_authenticated:
        user_info = f"""
        <div style="background: #34495e; padding: 15px; border-radius: 8px; margin-top: 20px;">
            <strong>Utente:</strong> {current_user.full_name} ({current_user.email})<br>
            <strong>Ruolo:</strong> {current_user.role}<br>
            <strong>Associazione:</strong> {current_user.association.name if current_user.association else 'Nessuna'}
        </div>
        """

    details_html = f"<p style='color: #95a5a6; margin-top: 15px;'>{details}</p>" if details else ""

    action_button = ""
    if action_url and action_text:
        action_button = f"""
        <a href="{action_url}" style="display: inline-block; margin-top: 25px; padding: 12px 30px;
           background: #3498db; color: white; text-decoration: none; border-radius: 5px;
           font-weight: bold; transition: background 0.3s;"
           onmouseover="this.style.background='#2980b9'"
           onmouseout="this.style.background='#3498db'">
            {action_text}
        </a>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - AGATA</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }}
            .container {{
                background: #2c3e50;
                color: #ecf0f1;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                max-width: 600px;
                text-align: center;
            }}
            h1 {{
                margin: 0 0 20px 0;
                font-size: 32px;
                color: #e74c3c;
            }}
            .icon {{
                font-size: 64px;
                margin-bottom: 20px;
            }}
            p {{
                font-size: 16px;
                line-height: 1.6;
                margin: 15px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">🚫</div>
            <h1>{title}</h1>
            <p>{message}</p>
            {details_html}
            {user_info}
            {action_button}
        </div>
    </body>
    </html>
    """


# ============================================================================
# IMPORT ROUTES
# ============================================================================

# Import routes
from . import routes
