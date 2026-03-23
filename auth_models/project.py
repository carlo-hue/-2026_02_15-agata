# agata/auth_models/project.py
"""
Project model - Progetti AGATA (workflow analisi stelle variabili)
"""
from sqlalchemy import String, Integer, Float, Double, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class Project(Base):
    """
    Progetto AGATA - workflow analisi stella variabile

    Stati workflow: incoming → available → assigned → in_review
                    → submitted_aavso → accepted/rejected_aavso
                    o cancelled in qualsiasi momento
    """
    __tablename__ = "agata_projects"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identificatori progetto
    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False,
                                              comment="Codice progetto univoco (es: AGATA-2024-001)")
    gaia_id: Mapped[str] = mapped_column(String(50), nullable=False,
                                         comment="Gaia DR3 source ID")
    tic_id: Mapped[int | None] = mapped_column(Integer, nullable=True,
                                               comment="TESS Input Catalog ID (cache da Gaia→TIC conversion)")

    # Associazione
    association_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_associations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Associazione proprietaria del progetto"
    )

    # Metadati stella
    title: Mapped[str | None] = mapped_column(String(500), nullable=True,
                                              comment="Descrizione breve stella/analisi")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                               comment="Fonte dati: ZTF, TESS, QLP, ASAS, etc.")
    ra: Mapped[float | None] = mapped_column(Double, nullable=True,
                                             comment="Right Ascension (gradi)")
    dec_deg: Mapped[float | None] = mapped_column(Double, nullable=True,
                                                   comment="Declination (gradi)")
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True,
                                                     comment="Magnitudine media")
    tic_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True,
                                                        comment="TESS magnitude (Tmag) da TIC")

    # Parametri fisici stella
    spectral_class: Mapped[str | None] = mapped_column(String(50), nullable=True,
                                                        comment="Classe spettrale (es: G2V, M3III)")
    teff: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                               comment="Temperatura effettiva (K) - salva anche origine catalogo")
    distance: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                   comment="Distanza (pc) - salva anche origine catalogo")
    luminosity: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                     comment="Luminosità (L☉) o Magnitudine - salva anche origine catalogo")
    radius: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                 comment="Raggio (R☉) - salva anche origine catalogo")
    mass: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                               comment="Massa (M☉) - salva anche origine catalogo")
    color_bv: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                   comment="Indice di colore B-V - salva anche origine catalogo")
    color_bprp: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                      comment="Indice di colore Gaia BP-RP - salva anche origine catalogo")

    # Parametri variabilità
    variable_type: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                       comment="Tipo di variabile proposto (es: RR Lyrae, Cepheid)")
    catalog_identifiers: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                             comment="Identificatori altri cataloghi (multi-riga)")
    variability_amplitude: Mapped[str | None] = mapped_column(String(100), nullable=True,
                                                                 comment="Ampiezza variabilità (mag) - salva anche origine catalogo")
    passband: Mapped[str | None] = mapped_column(String(50), nullable=True,
                                                 comment="Passband fotometrico (es: V, G)")
    period: Mapped[float | None] = mapped_column(Float, nullable=True,
                                                 comment="Periodo variabilità (giorni) - per variabili periodiche")
    epoch: Mapped[float | None] = mapped_column(Float, nullable=True,
                                                comment="Epoca massimo/minimo (JD) - per stelle periodiche")

    # Stato workflow AGATA
    state: Mapped[str] = mapped_column(
        SQLEnum('incoming', 'available', 'assigned', 'in_review', 'submitted_aavso',
                'accepted_aavso', 'rejected_aavso', 'cancelled', name='project_state'),
        nullable=False,
        default='incoming',
        comment="Stato attuale nel workflow AGATA/AAAAT"
    )

    # Assegnazione
    assigned_to: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID analyst assegnato"
    )
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                          comment="Data assegnazione")

    # Revisione
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID reviewer"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                          comment="Data revisione")
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                      comment="Note revisore")

    # Invio AAVSO
    submitted_aavso_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                                 comment="Data invio AAVSO")
    submitted_aavso_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID che ha inviato ad AAVSO"
    )
    aavso_response: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                        comment="Risposta AAVSO (JSON)")
    aavso_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                                comment="Data accettazione AAVSO")
    aavso_rejected_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                                comment="Data rifiuto AAVSO")

    # Cancellazione
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                           comment="Data cancellazione")
    cancelled_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID che ha cancellato"
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                             comment="Motivazione cancellazione")

    # Note generali
    notes: Mapped[str | None] = mapped_column(Text, nullable=True,
                                               comment="Note generali sul progetto")

    # Metadati
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True,
                                               comment="Dati aggiuntivi progetto (JSON)")

    # Relationships
    association: Mapped["Association"] = relationship("Association", back_populates="projects")
    assigned_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[assigned_to],
        back_populates="assigned_projects"
    )
    reviewer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="reviewed_projects"
    )

    def __repr__(self):
        return f"<Project(code='{self.project_code}', gaia_id='{self.gaia_id}', state='{self.state}')>"
