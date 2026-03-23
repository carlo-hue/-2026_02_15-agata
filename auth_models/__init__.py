"""
AGATA Authentication Models

Modelli SQLAlchemy per il sistema di autenticazione OAuth 2.0
Tabelle con prefisso agata_ per coesistenza con sistema legacy
"""

from .user import User
from .association import Association
from .oauth_token import OAuthToken
from .slack_channel import SlackChannel
from .project import Project
from .project_slack_thread import ProjectSlackThread
from .project_science_data import ProjectScienceData
from .project_output import ProjectOutput
from .audit_log import AuditLog
from .user_session import UserSession
from .system_config import SystemConfig
from .catalog_import import CatalogImport
from .magic_link_token import MagicLinkToken
from .star_assignment import StarAssignment
from .kb_sync_status import KBSyncStatus
from .kb_search_history import KBSearchHistory
from .vast_job import VastJob, VastResult
from .catalog_attribute import CatalogAttribute

__all__ = [
    'User',
    'Association',
    'OAuthToken',
    'SlackChannel',
    'Project',
    'ProjectSlackThread',
    'ProjectScienceData',
    'ProjectOutput',
    'AuditLog',
    'UserSession',
    'SystemConfig',
    'CatalogImport',
    'MagicLinkToken',
    'StarAssignment',
    'KBSyncStatus',
    'KBSearchHistory',
    'VastJob',
    'VastResult',
    'CatalogAttribute',
]
