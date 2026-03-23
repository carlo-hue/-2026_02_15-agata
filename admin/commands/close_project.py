# agata/admin/commands/close_project.py
"""
Command: Chiudi progetto (completamento con successo)
"""
from typing import Dict, Any
from datetime import datetime

from agata.admin.services.project_state_policy import AuditEventType
from .base_command import BaseCommand, CommandError


class CloseProjectCommand(BaseCommand):
    """
    Chiudi progetto dopo completamento con successo

    Pre-condizioni:
    - Progetto in stato: in_review o accepted_aavso
    - Utente ha permessi reviewer, admin o superuser

    Post-condizioni:
    - Se in_review: passa a 'accepted_aavso' (chiusura interna)
    - Se accepted_aavso: rimane 'accepted_aavso' (già chiuso)
    - reviewed_by = current_user.id
    - reviewed_at = now

    Note:
    - Rappresenta completamento positivo del workflow
    - Può includere note finali del reviewer
    """

    def __init__(self, db, project, current_user, notes: str = None, **kwargs):
        """
        Args:
            notes: Note finali del reviewer (opzionali)
        """
        super().__init__(db, project, current_user, **kwargs)
        self.notes = notes

    def get_action_name(self) -> str:
        return "close"

    def get_audit_event_type(self) -> str:
        return AuditEventType.PROJECT_CLOSED

    def _validate_specific(self) -> None:
        """Validazione specifica chiusura"""
        # Verifica stato permette chiusura
        allowed_states = ['in_review', 'accepted_aavso']
        if self.project.state not in allowed_states:
            raise CommandError(
                f"Impossibile chiudere progetto in stato '{self.project.state}'. "
                f"Stati validi: {', '.join(allowed_states)}"
            )

        # Verifica ruolo (solo reviewer, admin, superuser)
        if self.current_user.role not in ['reviewer', 'admin', 'superuser']:
            raise CommandError(
                f"Ruolo '{self.current_user.role}' non autorizzato a chiudere progetti. "
                "Solo reviewer, admin, superuser possono chiudere."
            )

    def _execute_db(self) -> Dict[str, Any]:
        """Esegue chiusura in DB"""
        # Se in_review, passa ad accepted_aavso
        if self.project.state == 'in_review':
            self.project.state = 'accepted_aavso'

        # Imposta dati revisione
        self.project.reviewed_by = self.current_user.id
        self.project.reviewed_at = datetime.utcnow()

        if self.notes:
            self.project.review_notes = self.notes

        self.db.flush()

        return {
            'reviewer_name': self.current_user.name,
            'has_notes': bool(self.notes)
        }

    def _get_audit_description(self, execution_data: Dict[str, Any]) -> str:
        notes_str = " con note" if execution_data['has_notes'] else ""
        return (f"Progetto {self.project.project_code} chiuso con successo da "
                f"{execution_data['reviewer_name']}{notes_str}")

    def _get_success_message(self, execution_data: Dict[str, Any]) -> str:
        return "Progetto chiuso con successo"
