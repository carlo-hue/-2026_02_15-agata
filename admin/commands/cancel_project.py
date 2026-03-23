# agata/admin/commands/cancel_project.py
"""
Command: Annulla progetto
"""
from typing import Dict, Any
from datetime import datetime

from agata.admin.services.project_state_policy import AuditEventType
from .base_command import BaseCommand, CommandError


class CancelProjectCommand(BaseCommand):
    """
    Annulla un progetto

    Pre-condizioni:
    - Progetto in stato: incoming, assigned, rejected_aavso
    - Utente ha permessi admin o superuser

    Post-condizioni:
    - Progetto passa a stato 'cancelled'
    - cancelled_at = now
    - cancelled_by = current_user.id
    - cancellation_reason salvata

    Note:
    - Stato finale - nessuna transizione possibile dopo cancellazione
    """

    def __init__(self, db, project, current_user, reason: str, **kwargs):
        """
        Args:
            reason: Motivazione cancellazione (obbligatoria)
        """
        super().__init__(db, project, current_user, **kwargs)
        self.reason = reason

    def get_action_name(self) -> str:
        return "cancel"

    def get_audit_event_type(self) -> str:
        return AuditEventType.PROJECT_CANCELLED

    def _validate_specific(self) -> None:
        """Validazione specifica cancellazione"""
        # Verifica motivazione fornita
        if not self.reason or len(self.reason.strip()) < 10:
            raise CommandError(
                "Motivazione cancellazione obbligatoria (minimo 10 caratteri)"
            )

        # Verifica stato permette cancellazione
        allowed_states = ['incoming', 'assigned', 'rejected_aavso']
        if self.project.state not in allowed_states:
            raise CommandError(
                f"Impossibile cancellare progetto in stato '{self.project.state}'. "
                f"Stati validi: {', '.join(allowed_states)}"
            )

    def _execute_db(self) -> Dict[str, Any]:
        """Esegue cancellazione in DB"""
        self.project.state = 'cancelled'
        self.project.cancelled_at = datetime.utcnow()
        self.project.cancelled_by = self.current_user.id
        self.project.cancellation_reason = self.reason

        self.db.flush()

        return {
            'reason': self.reason,
            'cancelled_by_name': self.current_user.name
        }

    def _get_audit_description(self, execution_data: Dict[str, Any]) -> str:
        return (f"Progetto {self.project.project_code} cancellato da "
                f"{execution_data['cancelled_by_name']}. "
                f"Motivo: {execution_data['reason']}")

    def _get_success_message(self, execution_data: Dict[str, Any]) -> str:
        return "Progetto cancellato con successo"
