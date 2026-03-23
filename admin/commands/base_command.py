# agata/admin/commands/base_command.py
"""
Base Command Pattern per azioni AGATA

Pattern:
1. Validate (stato, permessi, business logic)
2. Execute (DB transaction)
3. Audit (log evento)
4. Notify (Slack best-effort)
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

from agata.auth_models import Project, User, AuditLog
from agata.admin.services.project_state_policy import validate_action, get_next_state


@dataclass
class CommandResult:
    """
    Risultato esecuzione comando

    Attributes:
        success: True se comando eseguito con successo
        project_id: ID progetto modificato
        old_state: Stato precedente progetto
        new_state: Nuovo stato progetto
        message: Messaggio descrittivo
        slack_notified: True se notifica Slack inviata con successo
        slack_error: Eventuale errore Slack (non blocca successo comando)
        audit_log_id: ID record audit log creato
    """
    success: bool
    project_id: int
    old_state: str
    new_state: str
    message: str
    slack_notified: bool = False
    slack_error: Optional[str] = None
    audit_log_id: Optional[int] = None
    data: Optional[Dict[str, Any]] = None


class CommandError(Exception):
    """Eccezione per errori di validazione comando"""
    pass


class BaseCommand(ABC):
    """
    Classe base per tutti i comandi AGATA

    Pattern di esecuzione:
    1. validate() - Valida stato, permessi, business logic
    2. _execute_db() - Esegue modifiche DB in transaction
    3. _audit_log() - Crea record audit
    4. _notify_slack() - Notifica Slack (best-effort, non blocca)

    Esempio uso:
        >>> cmd = AssignAnalystCommand(db, project, analyst, current_user)
        >>> result = cmd.execute()
        >>> if result.success:
        >>>     print(f"Progetto assegnato a {analyst.name}")
    """

    def __init__(
        self,
        db: Session,
        project: Project,
        current_user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Args:
            db: SQLAlchemy session
            project: Progetto su cui agire
            current_user: Utente che esegue comando
            ip_address: IP origine richiesta (per audit)
            user_agent: User agent browser (per audit)
        """
        self.db = db
        self.project = project
        self.current_user = current_user
        self.ip_address = ip_address
        self.user_agent = user_agent

        self.old_state = project.state  # Salva stato originale

    @abstractmethod
    def get_action_name(self) -> str:
        """Ritorna nome azione (per policy validation e audit)"""
        pass

    @abstractmethod
    def get_audit_event_type(self) -> str:
        """Ritorna tipo evento audit (da AuditEventType)"""
        pass

    def validate(self) -> None:
        """
        Valida se comando può essere eseguito

        Raises:
            CommandError: Se validazione fallisce
        """
        # Validazione generica tramite policy
        is_valid, error_msg = validate_action(
            self.project,
            self.get_action_name(),
            self.current_user
        )

        if not is_valid:
            raise CommandError(error_msg)

        # Validazione specifica (override in subclass se necessario)
        self._validate_specific()

    def _validate_specific(self) -> None:
        """
        Validazione specifica del comando (override in subclass)

        Raises:
            CommandError: Se validazione fallisce
        """
        pass

    @abstractmethod
    def _execute_db(self) -> Dict[str, Any]:
        """
        Esegue modifiche DB (override in subclass)

        Returns:
            Dict con dati da passare a audit/notify

        Raises:
            Exception: Se esecuzione DB fallisce (triggera rollback)
        """
        pass

    def _audit_log(self, execution_data: Dict[str, Any], outcome: str = 'success') -> int:
        """
        Crea record audit log

        Args:
            execution_data: Dati esecuzione da _execute_db()
            outcome: 'success', 'error', 'partial'

        Returns:
            ID record audit log creato
        """
        audit = AuditLog(
            user_id=self.current_user.id,
            user_email=self.current_user.email,
            association_id=self.current_user.association_id,
            action=self.get_audit_event_type(),
            entity_type='project',
            entity_id=str(self.project.id),
            old_value=self.old_state,
            new_value=self.project.state,
            description=self._get_audit_description(execution_data),
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            outcome=outcome,
            created_at=datetime.utcnow()
        )

        self.db.add(audit)
        self.db.flush()  # Per ottenere l'ID
        return audit.id

    def _get_audit_description(self, execution_data: Dict[str, Any]) -> str:
        """
        Genera descrizione per audit log (override in subclass per personalizzare)

        Args:
            execution_data: Dati esecuzione

        Returns:
            Descrizione testuale
        """
        return f"{self.get_action_name()} su progetto {self.project.project_code}"

    def _notify_slack(self, execution_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Notifica Slack (best-effort - non blocca successo comando)

        Args:
            execution_data: Dati esecuzione

        Returns:
            Tuple (success, error_message)
        """
        # TODO: Implementare integrazione Slack
        # Per ora return success=False per non creare dipendenza
        return False, "Slack integration not implemented"

    def execute(self) -> CommandResult:
        """
        Esegue comando completo con pattern standard

        Returns:
            CommandResult con esito

        Raises:
            CommandError: Se validazione fallisce
            Exception: Se esecuzione DB fallisce
        """
        # 1. VALIDATE
        self.validate()

        try:
            # 2. EXECUTE DB (in transaction)
            execution_data = self._execute_db()

            # 3. AUDIT LOG
            audit_id = self._audit_log(execution_data, outcome='success')

            # Commit transaction
            self.db.commit()

            # 4. NOTIFY SLACK (best-effort, dopo commit DB)
            slack_success, slack_error = self._notify_slack(execution_data)

            # Se Slack fallisce, logga ma non rollback
            if not slack_success:
                # Aggiorna audit log con errore Slack
                try:
                    audit = self.db.query(AuditLog).get(audit_id)
                    if audit:
                        audit.outcome = 'partial'
                        audit.error_message = f"Slack notification failed: {slack_error}"
                        audit.slack_payload = {'error': slack_error}
                        self.db.commit()
                except Exception as e:
                    # Log ma non propagare errore
                    print(f"Error updating audit log with Slack error: {e}")

            return CommandResult(
                success=True,
                project_id=self.project.id,
                old_state=self.old_state,
                new_state=self.project.state,
                message=self._get_success_message(execution_data),
                slack_notified=slack_success,
                slack_error=slack_error,
                audit_log_id=audit_id,
                data=execution_data
            )

        except CommandError:
            # Errore validazione - propagare
            self.db.rollback()
            raise

        except Exception as e:
            # Errore DB - rollback e propagare
            self.db.rollback()

            # Log audit con outcome=error
            try:
                audit = AuditLog(
                    user_id=self.current_user.id,
                    user_email=self.current_user.email,
                    association_id=self.current_user.association_id,
                    action=self.get_audit_event_type(),
                    entity_type='project',
                    entity_id=str(self.project.id),
                    outcome='error',
                    error_message=str(e),
                    created_at=datetime.utcnow()
                )
                self.db.add(audit)
                self.db.commit()
            except:
                pass  # Non propagare errori di audit logging

            raise

    def _get_success_message(self, execution_data: Dict[str, Any]) -> str:
        """
        Genera messaggio di successo (override in subclass per personalizzare)

        Args:
            execution_data: Dati esecuzione

        Returns:
            Messaggio testuale
        """
        return f"Comando {self.get_action_name()} eseguito con successo"
