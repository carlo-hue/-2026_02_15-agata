# agata/auth/magic_link.py
"""
Magic Link Authentication Routes

Permette login senza password via email:
- /auth/magic-link/request - Richiede invio magic link
- /auth/magic-link/verify/<token> - Valida token e login
"""
from flask import Blueprint, request, jsonify, current_app, redirect, render_template_string
from flask_login import login_user
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from agata.db import SessionLocal
from agata.auth_models import User, MagicLinkToken, AuditLog, Association
from .email_service import send_magic_link_email

magic_link_bp = Blueprint('magic_link', __name__, url_prefix='/auth/magic-link')


# Template HTML per form richiesta magic link
REQUEST_FORM_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Login con Magic Link - AGATA</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 400px; margin: 100px auto; padding: 20px; }
        h1 { color: #333; }
        form { margin-top: 20px; }
        input[type="email"] { width: 100%; padding: 12px; margin: 10px 0;
                              border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }
        button { width: 100%; padding: 12px; background: #4285f4; color: white;
                 border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
        button:hover { background: #357abd; }
        .message { padding: 12px; margin: 10px 0; border-radius: 4px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        .back { display: block; margin-top: 20px; text-align: center; color: #666; }
    </style>
</head>
<body>
    <h1>Login con Magic Link</h1>
    <p>Inserisci la tua email per ricevere un link di accesso.</p>

    {% if message %}
    <div class="message {{ message_type }}">{{ message }}</div>
    {% endif %}

    {% if not sent %}
    <form method="POST" action="/auth/magic-link/request">
        <input type="email" name="email" placeholder="La tua email" required autofocus>
        <button type="submit">Invia Magic Link</button>
    </form>
    {% endif %}

    <a href="/" class="back">&larr; Torna alla homepage</a>
</body>
</html>
"""

# Template per conferma invio
SENT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Controlla la tua email - AGATA</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 400px; margin: 100px auto; padding: 20px; text-align: center; }
        h1 { color: #333; }
        .icon { font-size: 64px; margin: 20px 0; }
        .email { font-weight: bold; color: #4285f4; }
        .note { color: #666; font-size: 14px; margin-top: 20px; }
        .back { display: block; margin-top: 30px; color: #666; }
    </style>
</head>
<body>
    <div class="icon">📧</div>
    <h1>Controlla la tua email</h1>
    <p>Abbiamo inviato un link di accesso a:</p>
    <p class="email">{{ email }}</p>
    <p class="note">Il link scade tra 15 minuti.<br>Se non ricevi l'email, controlla la cartella spam.</p>
    <a href="/" class="back">&larr; Torna alla homepage</a>
</body>
</html>
"""

# Template errore
ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Errore - AGATA</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 400px; margin: 100px auto; padding: 20px; text-align: center; }
        h1 { color: #dc3545; }
        .icon { font-size: 64px; margin: 20px 0; }
        .back { display: block; margin-top: 30px; color: #666; }
        .retry { display: inline-block; margin-top: 20px; padding: 12px 24px;
                 background: #4285f4; color: white; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="icon">⚠️</div>
    <h1>{{ title }}</h1>
    <p>{{ message }}</p>
    <a href="/auth/magic-link/request" class="retry">Riprova</a>
    <a href="/" class="back">&larr; Torna alla homepage</a>
</body>
</html>
"""


@magic_link_bp.route('/request', methods=['GET', 'POST'])
def request_magic_link():
    """
    GET: Mostra form richiesta magic link
    POST: Invia magic link via email
    """
    if request.method == 'GET':
        return render_template_string(REQUEST_FORM_TEMPLATE, message=None, sent=False)

    # POST - processa richiesta
    email = request.form.get('email', '').lower().strip()

    if not email or '@' not in email:
        return render_template_string(
            REQUEST_FORM_TEMPLATE,
            message="Inserisci un'email valida",
            message_type="error",
            sent=False
        )

    db: Session = SessionLocal()

    try:
        # Cerca utente esistente
        user = db.query(User).filter_by(email=email).first()
        user_id = user.id if user else None

        # Invalida token precedenti per questa email
        db.query(MagicLinkToken).filter(
            MagicLinkToken.email == email,
            MagicLinkToken.is_used == False
        ).update({'is_used': True})

        # Genera nuovo token
        token = MagicLinkToken.generate(
            email=email,
            user_id=user_id,
            expires_minutes=15,
            ip_address=request.remote_addr
        )
        db.add(token)
        db.commit()

        # Invia email
        base_url = current_app.config.get('BASE_URL', request.host_url.rstrip('/'))
        magic_link_url = f"{base_url}/auth/magic-link/verify/{token.token}"

        send_success = send_magic_link_email(
            to_email=email,
            magic_link_url=magic_link_url,
            is_new_user=(user is None)
        )

        if not send_success:
            current_app.logger.error(f"Failed to send magic link email to {email}")
            # Non rivelare se l'invio è fallito per sicurezza
            # (potrebbe rivelare se l'email esiste o meno)

        # Log audit
        audit = AuditLog(
            user_id=user_id,
            user_email=email,
            action='magic_link_requested',
            entity_type='magic_link',
            entity_id=str(token.id),
            description=f"Magic link richiesto per {email}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
        db.add(audit)
        db.commit()

        # Mostra sempre conferma (anche se email non esiste, per sicurezza)
        return render_template_string(SENT_TEMPLATE, email=email)

    except Exception as e:
        db.rollback()
        current_app.logger.error(f"Error requesting magic link: {e}", exc_info=True)
        return render_template_string(
            REQUEST_FORM_TEMPLATE,
            message="Si è verificato un errore. Riprova più tardi.",
            message_type="error",
            sent=False
        )

    finally:
        db.close()


@magic_link_bp.route('/verify/<token>')
def verify_magic_link(token: str):
    """
    Verifica magic link e effettua login

    Args:
        token: Token dal magic link

    Returns:
        Redirect a dashboard o pagina errore
    """
    db: Session = SessionLocal()

    try:
        # Cerca token
        magic_token = db.query(MagicLinkToken).filter_by(token=token).first()

        if not magic_token:
            return render_template_string(
                ERROR_TEMPLATE,
                title="Link non valido",
                message="Il link non è valido. Potrebbe essere già stato utilizzato o è scaduto."
            )

        if not magic_token.is_valid:
            reason = "già utilizzato" if magic_token.is_used else "scaduto"
            return render_template_string(
                ERROR_TEMPLATE,
                title="Link non valido",
                message=f"Il link è {reason}. Richiedi un nuovo magic link."
            )

        # Token valido - cerca o crea utente
        email = magic_token.email

        if magic_token.user_id:
            # Utente esistente
            user = db.query(User).filter_by(id=magic_token.user_id).first()
            if not user or not user.is_active:
                return render_template_string(
                    ERROR_TEMPLATE,
                    title="Account disabilitato",
                    message="Il tuo account è stato disabilitato. Contatta l'amministratore."
                )
            is_new_user = False
        else:
            # Nuovo utente - crealo
            is_new_user = True

            # Determina se interno (@astrogen.it)
            is_internal = email.endswith('@astrogen.it')

            # Associazione di default
            association_id = None
            default_role = 'viewer'

            if is_internal:
                astrogen_assoc = db.query(Association).filter_by(slug='astrogen').first()
                if astrogen_assoc:
                    association_id = astrogen_assoc.id
                    default_role = 'analyst'

            # Estrai nome da email (best effort)
            name_part = email.split('@')[0]
            name_parts = name_part.replace('.', ' ').replace('_', ' ').split()
            name = name_parts[0].capitalize() if name_parts else email
            surname = name_parts[1].capitalize() if len(name_parts) > 1 else ''

            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                surname=surname,
                provider='magic_link',
                provider_user_id=email,  # Per magic link, usiamo email come ID
                is_internal=is_internal,
                association_id=association_id,
                role=default_role,
                is_active=True,
                email_verified=True,  # Magic link = email verificata
                last_login=datetime.utcnow(),
                last_login_ip=request.remote_addr,
            )
            db.add(user)
            db.flush()

            # Log creazione utente
            audit = AuditLog(
                user_id=user.id,
                user_email=user.email,
                association_id=user.association_id,
                action='user_created',
                entity_type='user',
                entity_id=user.id,
                new_value="provider=magic_link",
                description="Nuovo utente registrato via magic link",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
            )
            db.add(audit)

        # Aggiorna ultimo login
        user.last_login = datetime.utcnow()
        user.last_login_ip = request.remote_addr

        # Marca token come usato
        magic_token.mark_used(ip_address=request.remote_addr)

        # Log login
        audit = AuditLog(
            user_id=user.id,
            user_email=user.email,
            association_id=user.association_id,
            action='login',
            entity_type='user',
            entity_id=user.id,
            description="Login via magic link",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
        db.add(audit)

        db.commit()

        # Flask-Login: login utente
        login_user(user, remember=True)

        # Redirect a dashboard
        return redirect('/agata/variable-stars')

    except Exception as e:
        db.rollback()
        current_app.logger.error(f"Error verifying magic link: {e}", exc_info=True)
        return render_template_string(
            ERROR_TEMPLATE,
            title="Errore",
            message="Si è verificato un errore durante il login. Riprova."
        )

    finally:
        db.close()
