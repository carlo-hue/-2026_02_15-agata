# agata/admin/commands/assign_analyst.py
"""
Command: Assegna progetto a un analista
"""
from typing import Dict, Any, Optional
from datetime import datetime

from agata.auth_models import User
from agata.admin.services.project_state_policy import AuditEventType
from agata.auth.email_service import send_project_assignment_email
from .base_command import BaseCommand, CommandError


class AssignAnalystCommand(BaseCommand):
    """
    Assegna un progetto disponibile a un analista

    Pre-condizioni:
    - Progetto in stato 'available'
    - Analista appartiene alla stessa associazione del progetto
    - Utente corrente ha permessi per assegnare (admin, superuser)

    Post-condizioni:
    - Progetto passa a stato 'assigned'
    - assigned_to = analyst.id
    - assigned_at = now
    """

    def __init__(self, db, project, analyst: User, current_user: User, **kwargs):
        """
        Args:
            analyst: Utente a cui assegnare il progetto
        """
        super().__init__(db, project, current_user, **kwargs)
        self.analyst = analyst

    def get_action_name(self) -> str:
        return "assign"

    def get_audit_event_type(self) -> str:
        return AuditEventType.PROJECT_ASSIGNED

    def _validate_specific(self) -> None:
        """Validazione specifica assegnazione"""
        # Verifica progetto in stato 'available'
        if self.project.state != 'available':
            raise CommandError(
                f"Può assegnare solo progetti in stato 'available', "
                f"stato attuale: '{self.project.state}'"
            )

        # Verifica analista appartiene alla stessa associazione
        if self.analyst.association_id != self.project.association_id:
            raise CommandError(
                "Analista deve appartenere alla stessa associazione del progetto"
            )

        # Verifica analista è attivo
        if not self.analyst.is_active:
            raise CommandError("Analista non è attivo nel sistema")

        # Verifica ruolo analista
        if self.analyst.role not in ['analyst', 'reviewer', 'admin']:
            raise CommandError(
                f"Ruolo '{self.analyst.role}' non può essere assegnato a progetti. "
                "Ruoli validi: analyst, reviewer, admin"
            )

    def _execute_db(self) -> Dict[str, Any]:
        """Esegue assegnazione in DB"""
        self.project.state = 'assigned'
        self.project.assigned_to = self.analyst.id
        self.project.assigned_at = datetime.utcnow()

        self.db.flush()

        return {
            'analyst_id': self.analyst.id,
            'analyst_name': self.analyst.name,
            'analyst_email': self.analyst.email
        }

    def _get_audit_description(self, execution_data: Dict[str, Any]) -> str:
        return (f"Progetto {self.project.project_code} assegnato a "
                f"{execution_data['analyst_name']} ({execution_data['analyst_email']})")

    def _get_success_message(self, execution_data: Dict[str, Any]) -> str:
        return f"Progetto assegnato con successo a {execution_data['analyst_name']}"

    def _notify_slack(self, execution_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Notifica Slack e invia email all'analista assegnato
        """
        # Invia email di notifica all'analista
        try:
            email_sent = send_project_assignment_email(
                to_email=self.analyst.email,
                analyst_name=self.analyst.full_name or self.analyst.name,
                project_code=self.project.project_code,
                project_title=self.project.title or self.project.gaia_id or "Stella variabile",
                assigned_by=self.current_user.full_name or self.current_user.name
            )
            if not email_sent:
                return False, "Invio email fallito"
        except Exception as e:
            return False, f"Errore invio email: {str(e)}"

        # TODO: Implementare anche notifica Slack
        return True, None
