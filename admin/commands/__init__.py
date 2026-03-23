# agata/admin/commands/__init__.py
"""
Command Pattern per azioni sui progetti AGATA

Ogni comando:
1. Valida lo stato e i permessi
2. Aggiorna il database
3. Genera eventi di audit
4. Notifica Slack (best-effort)

Principio: Idempotenza e separazione concerns (DB success != Slack success)
"""

from .base_command import BaseCommand, CommandResult, CommandError
from .assign_analyst import AssignAnalystCommand
from .send_to_review import SendToReviewCommand
from .cancel_project import CancelProjectCommand
from .close_project import CloseProjectCommand

__all__ = [
    'BaseCommand',
    'CommandResult',
    'CommandError',
    'AssignAnalystCommand',
    'SendToReviewCommand',
    'CancelProjectCommand',
    'CloseProjectCommand',
]
