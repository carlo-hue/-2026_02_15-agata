# agata/auth/oauth_providers.py
"""
OAuth 2.0 Providers Configuration

Configura i provider OAuth supportati:
- Google (Google Workspace + Gmail)
- Slack (workspace integration)
- GitHub (opzionale)
"""
from authlib.integrations.flask_client import OAuth

# Istanza OAuth globale
oauth = OAuth()


def init_oauth(app):
    """
    Inizializza i provider OAuth con configurazione da Flask app

    Args:
        app: Istanza Flask app

    Returns:
        Istanza OAuth configurata
    """
    oauth.init_app(app)

    # ========================================================================
    # GOOGLE OAUTH
    # ========================================================================
    # Supporta Google Workspace (@astrogen.it) e Gmail generici
    # Scopes: openid, email, profile
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    # ========================================================================
    # SLACK OAUTH
    # ========================================================================
    # Integrazione Slack workspace
    # Scopes: users:read, users:read.email, channels:read, chat:write, commands
    oauth.register(
        name='slack',
        client_id=app.config.get('SLACK_CLIENT_ID'),
        client_secret=app.config.get('SLACK_CLIENT_SECRET'),
        authorize_url='https://slack.com/oauth/v2/authorize',
        authorize_params=None,
        access_token_url='https://slack.com/api/oauth.v2.access',
        access_token_params=None,
        refresh_token_url=None,
        client_kwargs={
            'scope': 'users:read users:read.email channels:read chat:write commands'
        }
    )

    # ========================================================================
    # GITHUB OAUTH (opzionale)
    # ========================================================================
    # Per sviluppatori e contributori esterni
    # Scopes: user:email
    if app.config.get('GITHUB_CLIENT_ID'):
        oauth.register(
            name='github',
            client_id=app.config.get('GITHUB_CLIENT_ID'),
            client_secret=app.config.get('GITHUB_CLIENT_SECRET'),
            authorize_url='https://github.com/login/oauth/authorize',
            authorize_params=None,
            access_token_url='https://github.com/login/oauth/access_token',
            access_token_params=None,
            api_base_url='https://api.github.com/',
            client_kwargs={
                'scope': 'user:email'
            }
        )

    return oauth


def get_user_info_from_token(provider: str, token: dict) -> dict:
    """
    Ottiene informazioni utente dal provider OAuth

    Args:
        provider: Nome provider ('google', 'slack', 'github')
        token: Token dict dal provider

    Returns:
        Dict con user info normalizzato:
        {
            'provider_user_id': str,
            'email': str,
            'name': str,
            'avatar_url': str,
        }

    Raises:
        ValueError: Provider non supportato
    """
    client = oauth.create_client(provider)

    if provider == 'google':
        # Google OpenID Connect
        resp = client.get('https://www.googleapis.com/oauth2/v3/userinfo')
        resp.raise_for_status()
        user_info = resp.json()

        return {
            'provider_user_id': user_info['sub'],
            'email': user_info['email'],
            'name': user_info.get('name', user_info['email']),
            'avatar_url': user_info.get('picture'),
        }

    elif provider == 'slack':
        # Slack Users API
        # Nota: Slack OAuth v2 restituisce user info direttamente nel token response
        # ma possiamo anche chiamare users.identity
        resp = client.get('https://slack.com/api/users.identity', token=token)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('ok'):
            raise ValueError(f"Slack API error: {data.get('error')}")

        user_info = data['user']

        return {
            'provider_user_id': user_info['id'],
            'email': user_info['email'],
            'name': user_info.get('name', user_info['email']),
            'avatar_url': user_info.get('image_192') or user_info.get('image_72'),
        }

    elif provider == 'github':
        # GitHub User API
        resp = client.get('user', token=token)
        resp.raise_for_status()
        user_info = resp.json()

        # GitHub email potrebbe essere None se privata
        email = user_info.get('email')
        if not email:
            # Fallback: prendi prima email verificata
            resp_emails = client.get('user/emails', token=token)
            resp_emails.raise_for_status()
            emails = resp_emails.json()
            verified_emails = [e for e in emails if e.get('verified')]
            if verified_emails:
                email = verified_emails[0]['email']
            else:
                raise ValueError("No verified email found for GitHub user")

        return {
            'provider_user_id': str(user_info['id']),
            'email': email,
            'name': user_info.get('name') or user_info['login'],
            'avatar_url': user_info.get('avatar_url'),
        }

    else:
        raise ValueError(f"Unsupported OAuth provider: {provider}")
