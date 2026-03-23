# agata/auth/routes.py
"""
Authentication Routes

Gestisce il flusso OAuth 2.0:
- /auth/login/<provider> - Inizia flusso OAuth
- /auth/callback/<provider> - Callback OAuth
- /auth/logout - Logout utente
- /api/auth/me - Info utente corrente
"""
from flask import Blueprint, redirect, url_for, request, session, jsonify, current_app, make_response
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from agata.db import SessionLocal
from agata.auth_models import User, OAuthToken, Association, AuditLog
from .oauth_providers import oauth, get_user_info_from_token

# Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login/<provider>')
def login(provider):
    """
    Inizia flusso OAuth con provider selezionato

    Args:
        provider: 'google', 'slack', 'github'

    Returns:
        Redirect to OAuth provider consent screen
    """
    if provider not in ['google', 'slack', 'github']:
        return jsonify({"error": "Provider non supportato"}), 400

    # URL callback dopo autorizzazione
    redirect_uri = url_for('auth.callback', provider=provider, _external=True, _scheme='https')

    # Crea client OAuth per provider
    client = oauth.create_client(provider)
    if not client:
        return jsonify({"error": f"Provider {provider} non configurato"}), 500

    # Redirect a pagina autorizzazione provider
    return client.authorize_redirect(redirect_uri)


@auth_bp.route('/callback/<provider>')
def callback(provider):
    """
    Callback OAuth dopo autorizzazione utente

    Riceve authorization code, lo scambia per access_token,
    crea/aggiorna utente nel DB, effettua login

    Args:
        provider: 'google', 'slack', 'github'

    Returns:
        Redirect to dashboard or error page
    """
    db: Session = SessionLocal()

    try:
        # Ottieni access token
        client = oauth.create_client(provider)
        token = client.authorize_access_token()

        # Ottieni informazioni utente dal provider
        try:
            user_info = get_user_info_from_token(provider, token)
        except Exception as e:
            current_app.logger.error(f"Error getting user info from {provider}: {e}")
            return jsonify({"error": "Errore recupero informazioni utente"}), 500

        # Estrai dati
        provider_user_id = user_info['provider_user_id']
        email = user_info['email']
        name_full = user_info['name']
        avatar_url = user_info.get('avatar_url')

        # Split name in nome/cognome (best effort)
        name_parts = name_full.split(' ', 1) if name_full else [email, '']
        name = name_parts[0]
        surname = name_parts[1] if len(name_parts) > 1 else ''

        # Check se utente esiste (by provider + provider_user_id)
        user = db.query(User).filter_by(
            provider=provider,
            provider_user_id=provider_user_id
        ).first()

        is_new_user = False

        if not user:
            # Nuovo utente - creiamo record
            is_new_user = True

            # Determina se utente interno (@astrogen.it)
            is_internal = email.endswith('@astrogen.it')

            # Determina associazione di default
            # - Utenti @astrogen.it → AstroGen APS (id=1)
            # - Altri → NULL (devono essere assegnati da admin)
            association_id = None
            default_role = 'viewer'

            if is_internal:
                astrogen_assoc = db.query(Association).filter_by(
                    slug='astrogen'
                ).first()
                if astrogen_assoc:
                    association_id = astrogen_assoc.id
                    default_role = 'analyst'  # Soci interni partono come analyst

            # Crea nuovo utente
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                surname=surname,
                avatar_url=avatar_url,
                provider=provider,
                provider_user_id=provider_user_id,
                is_internal=is_internal,
                association_id=association_id,
                role=default_role,
                is_active=True,
                email_verified=True,  # OAuth providers già verificano email
                last_login=datetime.utcnow(),
                last_login_ip=request.remote_addr,
            )
            db.add(user)
            db.flush()  # Get user.id

            # Log audit
            audit = AuditLog(
                user_id=user.id,
                user_email=user.email,
                association_id=user.association_id,
                action='user_created',
                entity_type='user',
                entity_id=user.id,
                new_value=f"provider={provider}",
                description=f"Nuovo utente registrato via {provider}",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
            )
            db.add(audit)

        else:
            # Utente esistente - aggiorniamo dati
            user.name = name
            user.surname = surname
            user.avatar_url = avatar_url
            user.last_login = datetime.utcnow()
            user.last_login_ip = request.remote_addr

        # Salva/aggiorna token OAuth
        oauth_token = db.query(OAuthToken).filter_by(
            user_id=user.id,
            provider=provider
        ).first()

        if not oauth_token:
            oauth_token = OAuthToken(
                user_id=user.id,
                provider=provider,
                access_token=token['access_token'],
                refresh_token=token.get('refresh_token'),
                token_type=token.get('token_type', 'Bearer'),
                expires_at=datetime.fromtimestamp(token['expires_at']) if 'expires_at' in token else None,
                scope=token.get('scope'),
            )
            db.add(oauth_token)
        else:
            oauth_token.access_token = token['access_token']
            oauth_token.refresh_token = token.get('refresh_token')
            oauth_token.expires_at = datetime.fromtimestamp(token['expires_at']) if 'expires_at' in token else None
            oauth_token.scope = token.get('scope')
            oauth_token.updated_at = datetime.utcnow()

        # Commit DB
        db.commit()

        # Log login
        if not is_new_user:
            audit = AuditLog(
                user_id=user.id,
                user_email=user.email,
                association_id=user.association_id,
                action='login',
                entity_type='user',
                entity_id=user.id,
                description=f"Login via {provider}",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
            )
            db.add(audit)
            db.commit()

        # Flask-Login: login utente nella sessione
        login_user(user, remember=True)

        # Redirect to admin dashboard
        return redirect(url_for('admin.list_projects'))

    except Exception as e:
        db.rollback()
        current_app.logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        return jsonify({"error": "Errore durante autenticazione"}), 500

    finally:
        db.close()


@auth_bp.route('/logout')
@login_required
def logout():
    """
    Logout utente

    Rimuove sessione e redirect a homepage
    """
    current_app.logger.info(f"Logout request from user: {current_user.email}")
    db: Session = SessionLocal()

    try:
        # Log audit
        audit = AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=current_user.association_id,
            action='logout',
            entity_type='user',
            entity_id=current_user.id,
            description="Logout",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
        db.add(audit)
        db.commit()

    except Exception as e:
        current_app.logger.error(f"Error logging logout: {e}")
    finally:
        db.close()

    current_app.logger.info(f"User logged out successfully, redirecting to /")

    # Flask-Login: logout (this clears the remember cookie internally)
    logout_user()

    # Clear all session data
    for key in list(session.keys()):
        session.pop(key)

    # Tell Flask not to save the session (important!)
    session.modified = False

    # Create response
    response = make_response(redirect('/'))

    # Get security settings from app config
    is_secure = current_app.config.get('SESSION_COOKIE_SECURE', False)

    # Force delete session cookie by setting it to empty with past expiry
    response.set_cookie(
        'session',
        value='',
        expires=0,
        max_age=0,
        path='/',
        domain=None,
        secure=is_secure,
        httponly=True,
        samesite='Lax'
    )

    # Force delete remember cookie
    response.set_cookie(
        'remember',
        value='',
        expires=0,
        max_age=0,
        path='/',
        domain=None,
        secure=is_secure,
        httponly=True,
        samesite='Lax'
    )

    return response


@auth_bp.route('/me')
@login_required
def me():
    """
    API endpoint: info utente corrente

    Returns:
        JSON con dati utente loggato
    """
    user_data = {
        'id': current_user.id,
        'email': current_user.email,
        'name': current_user.name,
        'surname': current_user.surname,
        'full_name': current_user.full_name,
        'avatar_url': current_user.avatar_url,
        'role': current_user.role,
        'is_internal': current_user.is_internal,
        'is_active': current_user.is_active,
        'association_id': current_user.association_id,
        'created_at': current_user.created_at.isoformat() if current_user.created_at else None,
        'last_login': current_user.last_login.isoformat() if current_user.last_login else None,
    }

    # Include association info if present
    if current_user.association:
        user_data['association'] = {
            'id': current_user.association.id,
            'name': current_user.association.name,
            'slug': current_user.association.slug,
            'type': current_user.association.type,
        }

    return jsonify(user_data)
