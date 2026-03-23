# agata/admin/commands/send_to_review.py
"""
Command: Invia progetto in revisione
"""
from typing import Dict, Any
from datetime import datetime

from agata.admin.services.project_state_policy import AuditEventType
from .base_command import BaseCommand, CommandError


class SendToReviewCommand(BaseCommand):
    """
    Invia un progetto assegnato in revisione scientifica

    Pre-condizioni:
    - Progetto in stato 'assigned'
    - Progetto ha un analista assegnato
    - Utente corrente è l'analista assegnato o ha permessi superiori

    Post-condizioni:
    - Progetto passa a stato 'in_review'
    - reviewed_at = now (opzionale, o solo quando completata)

    Note:
    - Questo comando può essere eseguito dall'analista stesso
      per sottoporre il proprio lavoro a revisione
    """

    def get_action_name(self) -> str:
        return "send_to_review"

    def get_audit_event_type(self) -> str:
        return AuditEventType.PROJECT_SENT_TO_REVIEW

    def _validate_specific(self) -> None:
        """Validazione specifica invio in review"""
        # Verifica progetto in stato 'assigned'
        if self.project.state != 'assigned':
            raise CommandError(
                f"Può inviare in review solo progetti in stato 'assigned', "
                f"stato attuale: '{self.project.state}'"
            )

        # Verifica progetto assegnato
        if not self.project.assigned_to:
            raise CommandError("Progetto non assegnato - impossibile inviare in review")

        # Se utente è analyst, può inviare solo propri progetti
        if self.current_user.role == 'analyst':
            if self.project.assigned_to != self.current_user.id:
                raise CommandError("Analyst può inviare in review solo propri progetti")

    def _execute_db(self) -> Dict[str, Any]:
        """Esegue invio in review in DB"""
        self.project.state = 'in_review'
        # reviewed_at viene impostato quando review è completata, non ora

        self.db.flush()

        return {
            'assigned_to': self.project.assigned_to,
            'assigned_user_name': self.db.query(self.db.query.User).get(self.project.assigned_to).name if self.project.assigned_to else None
        }

    def _get_audit_description(self, execution_data: Dict[str, Any]) -> str:
        return f"Progetto {self.project.project_code} inviato in revisione scientifica"

    def _get_success_message(self, execution_data: Dict[str, Any]) -> str:
        return "Progetto inviato in revisione con successo"
