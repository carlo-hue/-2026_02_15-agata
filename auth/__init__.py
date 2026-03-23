"""
AGATA Authentication Module

OAuth 2.0 authentication with multi-provider support:
- Google OAuth (Workspace + Gmail)
- Slack OAuth (workspace integration)
- GitHub OAuth (optional, for developers)
"""

from .oauth_providers import oauth, init_oauth
from .routes import auth_bp
from .magic_link import magic_link_bp
from .decorators import login_required, require_role, require_permission

__all__ = [
    'oauth',
    'init_oauth',
    'auth_bp',
    'magic_link_bp',
    'login_required',
    'require_role',
    'require_permission',
]
