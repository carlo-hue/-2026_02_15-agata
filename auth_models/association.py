# agata/auth_models/association.py
"""
Association model - Rappresenta enti/organizzazioni che usano AGATA
"""
from sqlalchemy import String, Boolean, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class Association(Base):
    """
    Ente/Organizzazione che utilizza AGATA

    Esempi:
    - AstroGen APS (internal)
    - Gruppo Variabili Toscane (partner)
    - Liceo Scientifico XYZ (school)
    """
    __tablename__ = "agata_associations"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Identificatori
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False,
                                      comment="Nome completo associazione")
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False,
                                      comment="Identificatore URL-safe per namespace Slack")

    # Tipologia
    type: Mapped[str] = mapped_column(
        SQLEnum('internal', 'partner', 'school', 'individual', name='association_type'),
        default='partner',
        comment="Tipologia ente"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True,
                                            comment="Ente attivo nel sistema")

    # Referente
    referente_email: Mapped[str | None] = mapped_column(String(255), nullable=True,
                                                         comment="Email referente ente")
    referente_name: Mapped[str | None] = mapped_column(String(255), nullable=True,
                                                        comment="Nome referente ente")

    # Configurazione Slack
    slack_namespace: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Namespace per canali Slack (es: gvt → ag-gvt-coord)"
    )
    slack_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Se False, disabilita integrazione Slack (no canali, no thread, no notifiche)"
    )

    # Metadati
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True,
                                                   comment="Configurazioni specifiche ente (JSON)")

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="association")
    slack_channels: Mapped[list["SlackChannel"]] = relationship("SlackChannel", back_populates="association")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="association")
    star_assignments: Mapped[list["StarAssignment"]] = relationship("StarAssignment", back_populates="association")

    def __repr__(self):
        return f"<Association(id={self.id}, name='{self.name}', slug='{self.slug}', type='{self.type}')>"

    @property
    def slack_channel_prefix(self):
        """Prefisso per i canali Slack di questa associazione"""
        return self.slack_namespace or self.slug

    def get_slack_channel_name(self, channel_type: str) -> str:
        """
        Genera il nome del canale Slack secondo lo schema AGATA

        Args:
            channel_type: 'coord', 'lavori', 'review'

        Returns:
            Nome canale (es: 'ag-gvt-coord', 'ag-gvt-lavori', 'ag-gvt-review')
        """
        prefix = self.slack_channel_prefix
        # TUTTI i canali AGATA iniziano con 'ag-'
        if channel_type == 'coord':
            return f"ag-{prefix}-coord"
        elif channel_type == 'lavori':
            return f"ag-{prefix}-lavori"  # Cambiato da tag- a ag-
        elif channel_type == 'review':
            return f"ag-{prefix}-review"  # Cambiato da tag- a ag-
        else:
            raise ValueError(f"Invalid channel_type: {channel_type}")
