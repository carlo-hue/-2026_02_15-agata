# agata/auth_models/audit_log.py
from sqlalchemy import String, Integer, ForeignKey, Text, BigInteger, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from agata.models import Base


class AuditLog(Base):
    """
    Log audit per compliance e debug - traccia tutte le azioni nel sistema
    """
    __tablename__ = "agata_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Chi ha eseguito l'azione
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="FK -> agata_users")
    user_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email utente (denormalizzata per storico)"
    )
    association_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Associazione utente")

    # Cosa è stato fatto
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Azione eseguita (es: project_assigned, slack_message_sent)"
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Tipo entità (project, user, association, channel)"
    )
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="ID entità modificata")

    # Dettagli modifiche
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Stato precedente (JSON)")
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Nuovo stato (JSON)")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Descrizione azione")

    # Contesto tecnico
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="IP origine richiesta")
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True, comment="User agent browser")
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Request ID per correlazione"
    )

    # Integrazione Slack
    slack_payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Payload Slack ridotto: {channel_id, thread_ts, message_ts, error}"
    )

    # Outcome dell'azione
    outcome: Mapped[str] = mapped_column(
        SQLEnum('success', 'error', 'partial', name='audit_outcome'),
        nullable=False,
        default='success',
        comment="Esito: success (OK) | error (fallimento) | partial (parziale)"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Messaggio errore dettagliato se outcome != success"
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        comment="Timestamp evento"
    )

    def __repr__(self):
        return f"<AuditLog(action='{self.action}', entity='{self.entity_type}:{self.entity_id}', outcome='{self.outcome}')>"
