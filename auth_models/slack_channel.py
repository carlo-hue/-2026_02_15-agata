# agata/auth_models/slack_channel.py
"""
Slack Channel model - Canali Slack workspace AGATA
"""
from sqlalchemy import String, Integer, Boolean, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class SlackChannel(Base):
    """
    Canale Slack per un'associazione

    Schema AGATA: ogni associazione ha 2-3 canali fissi:
    - ag-{slug}-coord (coordinamento)
    - tag-{slug}-lavori (analisi available/assigned)
    - tag-{slug}-review (revisione scientifica)
    """
    __tablename__ = "agata_slack_channels"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Riferimento associazione
    association_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_associations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Associazione proprietaria del canale"
    )

    # Identificatori Slack
    channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False,
                                            comment="Slack channel ID (es: C01234ABC)")
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False,
                                              comment="Nome canale completo (es: ag-gvt-coord)")
    team_id: Mapped[str | None] = mapped_column(String(50), nullable=True,
                                                 comment="Slack workspace ID")

    # Tipologia canale secondo schema AGATA
    channel_type: Mapped[str] = mapped_column(
        SQLEnum('coord', 'lavori', 'review', name='slack_channel_type'),
        nullable=False,
        comment="coord: coordinamento | lavori: analisi available/assigned | review: revisione scientifica"
    )

    # Audit
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID creatore"
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True,
                                            comment="Canale attivo")

    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True,
                                                   comment="Configurazioni canale-specifiche (JSON)")

    # Relationships
    association: Mapped["Association"] = relationship("Association", back_populates="slack_channels")

    def __repr__(self):
        return f"<SlackChannel(id={self.id}, name='{self.channel_name}', type='{self.channel_type}')>"
