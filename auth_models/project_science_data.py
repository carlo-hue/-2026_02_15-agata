# agata/auth_models/project_science_data.py
"""
Project Science Data model - Dati scientifici strutturati per progetti AGATA
Separati dalla conversazione Slack per garantire persistenza e ricercabilità
"""
from sqlalchemy import String, Integer, Float, Double, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class ProjectScienceData(Base):
    """
    Dati scientifici strutturati per un progetto AGATA

    Relazione 1:1 con Project - ogni progetto ha un solo record di dati scientifici
    Questi dati NON devono stare solo in Slack, ma in DB per query e reportistica
    """
    __tablename__ = "agata_project_science_data"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key (1:1 con Project)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="FK -> agata_projects (relazione 1:1)"
    )

    # ========================================================================
    # DATASET
    # ========================================================================
    dataset_drive_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Link Google Drive cartella/file dataset principale"
    )
    dataset_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Tipo dati: lightcurve, spectrum, photometry, timeseries, etc."
    )
    dataset_uploaded_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Data caricamento dataset"
    )
    dataset_uploaded_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK -> agata_users che ha caricato dataset"
    )
    dataset_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Note sul dataset (qualità, problemi, filtri applicati)"
    )

    # ========================================================================
    # CLASSIFICAZIONE E RISULTATI
    # ========================================================================
    classification: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Classificazione variabile proposta (es: RRab, EA, EB, Delta_Sct, DCEP)"
    )
    period_days: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
        comment="Periodo stimato in giorni"
    )
    period_uncertainty: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
        comment="Incertezza periodo (±giorni)"
    )
    epoch_jd: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
        comment="Epoca di riferimento (Julian Date)"
    )
    amplitude_mag: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Ampiezza variazione in magnitudini"
    )
    confidence_level: Mapped[str | None] = mapped_column(
        SQLEnum('low', 'medium', 'high', name='confidence_level'),
        nullable=True,
        comment="Livello confidenza analisi: low/medium/high"
    )

    # ========================================================================
    # NOTE SCIENTIFICHE STRUTTURATE
    # ========================================================================
    scientific_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Note analista: osservazioni, incertezze, problemi, commenti scientifici"
    )
    analysis_method: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Metodo analisi utilizzato (es: Lomb-Scargle periodogram, PDM, etc.)"
    )

    # ========================================================================
    # DATI AGGIUNTIVI FLESSIBILI
    # ========================================================================
    additional_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Altri parametri scientifici in formato JSON flessibile"
    )

    # ========================================================================
    # AUDIT
    # ========================================================================
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        comment="Data creazione record"
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Data ultimo aggiornamento"
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK -> agata_users ultimo aggiornamento"
    )

    # Relationships
    # project: Mapped["Project"] = relationship("Project", back_populates="science_data")

    def __repr__(self):
        return (f"<ProjectScienceData(project_id={self.project_id}, "
                f"classification='{self.classification}', "
                f"period={self.period_days})>")
