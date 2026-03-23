# agata/auth_models/project_slack_thread.py
from sqlalchemy import String, Integer, Boolean, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from agata.models import Base


class ProjectSlackThread(Base):
    """
    Mapping tra progetti AGATA e contesti Slack (thread o canale dedicato)
    """
    __tablename__ = "agata_project_slack_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK -> agata_projects"
    )
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="Slack channel ID")
    thread_ts: Mapped[str] = mapped_column(String(50), nullable=False, comment="Thread timestamp")
    message_ts: Mapped[str] = mapped_column(String(50), nullable=False, comment="Message timestamp")

    # Tipo contesto Slack (thread vs canale dedicato)
    slack_type: Mapped[str] = mapped_column(
        SQLEnum('thread', 'channel', name='slack_context_type'),
        nullable=False,
        default='thread',
        comment="Tipo contesto: thread in canale lavori o canale dedicato"
    )

    # Tracking ultimo messaggio
    last_message_ts: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Timestamp ultimo messaggio ricevuto"
    )
    last_message_preview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Preview testuale ultimo messaggio (cache per UI)"
    )

    # Stato sincronizzato con progetto
    current_state: Mapped[str] = mapped_column(
        SQLEnum('incoming', 'available', 'assigned', 'in_review', 'submitted_aavso',
                'accepted_aavso', 'rejected_aavso', 'cancelled', name='thread_state'),
        nullable=False,
        comment="Stato denormalizzato (sync con agata_projects.state)"
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="Thread attivo")

    def __repr__(self):
        return f"<ProjectSlackThread(project_id={self.project_id}, type='{self.slack_type}', channel='{self.channel_id}')>"
