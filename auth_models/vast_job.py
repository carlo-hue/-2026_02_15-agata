# agata/auth_models/vast_job.py
"""
VAST Job model - Tracciamento lavori di automazione VAST

Gestisce il workflow di analisi di immagini astronomiche FITS:
- Download da Google Drive
- Validazione WCS (astrometria)
- Esecuzione VAST per fotometria
- Upload risultati a database
"""
from sqlalchemy import String, Integer, BigInteger, Float, Double, Boolean, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class VastJob(Base):
    """
    Traccia le sessioni di elaborazione VAST.

    Workflow:
    1. Superuser crea job (pending)
    2. Download immagini da Google Drive (downloading)
    3. Validazione WCS con Astropy (validating)
    4. Esecuzione VAST (vast_analysis)
    5. Upload risultati a DB (uploading)
    6. Completamento (completed) o errore (failed)
    """
    __tablename__ = "agata_vast_jobs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identificazione job
    job_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False,
        comment="Codice univoco job (es. VAST-2026-0001)"
    )
    target_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Nome target astronomico"
    )
    target_ra: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Right Ascension target (gradi)"
    )
    target_dec: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Declination target (gradi)"
    )

    # Parametri sorgente
    source_type: Mapped[str] = mapped_column(
        SQLEnum('drive_folder', 'local_path', 'url', name='vast_source_type'),
        nullable=False,
        comment="Tipo sorgente: drive_folder, local_path, url"
    )
    source_location: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Google Drive folder ID, local path, o URL"
    )
    processing_params: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Parametri VAST: {threshold, field_size, ...}"
    )

    # Stato macchina workflow
    state: Mapped[str] = mapped_column(
        SQLEnum('pending', 'downloading', 'validating',
                'vast_analysis', 'crossmatching', 'uploading', 'completed',
                'failed', 'cancelled', name='vast_job_state'),
        default='pending',
        nullable=False,
        comment="Stato corrente del workflow"
    )
    progress_pct: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Percentuale completamento (0-100)"
    )
    current_step: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Descrizione step attuale"
    )

    # Metriche elaborazione
    images_downloaded: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Numero immagini scaricate"
    )
    images_solved: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Numero immagini con WCS validato"
    )
    candidates_found: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Numero candidati variabili trovati"
    )
    stars_uploaded: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Numero stelle caricate nel database"
    )

    # Tracking file
    downloaded_files: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Lista file scaricati: {paths: [...]}"
    )
    output_files: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="File output generati: {plots: [...], data: [...]}"
    )

    # Gestione errori
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Messaggio errore in caso di fallimento"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Numero tentativi riavvio"
    )

    # Utente richiedente
    requested_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID che ha richiesto l'analisi"
    )

    # Link a Project creato (opzionale)
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="SET NULL"),
        nullable=True,
        comment="Project AGATA creato da questa analisi"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False,
        comment="Data creazione job"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Data inizio elaborazione"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Data completamento job"
    )

    # Relationships
    requester: Mapped["User"] = relationship(
        "User",
        foreign_keys=[requested_by],
        lazy="joined"
    )
    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="joined"
    )
    results: Mapped[list["VastResult"]] = relationship(
        "VastResult",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<VastJob(id={self.id}, code='{self.job_code}', state='{self.state}')>"

    @property
    def is_running(self) -> bool:
        """True se il job è in elaborazione."""
        return self.state in ['downloading', 'validating', 'vast_analysis', 'crossmatching', 'uploading']

    @property
    def is_failed(self) -> bool:
        """True se il job è fallito."""
        return self.state == 'failed'

    @property
    def duration_seconds(self) -> float | None:
        """Durata job in secondi."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class VastResult(Base):
    """
    Risultato individuale di candidato stella variabile da VAST.
    """
    __tablename__ = "agata_vast_results"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key al job
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_vast_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="Job ID padre"
    )

    # Identificazione stella
    vast_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Identificativo VAST"
    )
    gaia_source_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="Gaia DR3 source ID"
    )
    ra: Mapped[float] = mapped_column(
        Double, nullable=False,
        comment="Right Ascension (gradi)"
    )
    decl: Mapped[float] = mapped_column(
        Double, nullable=False,
        comment="Declination (gradi)"
    )

    # Fotometria
    mean_mag: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Magnitudine media"
    )
    mag_err: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Errore magnitudine"
    )
    std_dev: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Deviazione standard magnitudini"
    )
    num_observations: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Numero osservazioni"
    )

    # Metriche variabilità
    variability_index: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Indice variabilità"
    )
    chi_squared: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Chi-quadrato fit"
    )
    period: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Periodo rilevato (giorni)"
    )

    # Variability indices e coordinate pixel
    variability_indices: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="All 31 VAST variability indices as JSON dict"
    )
    x_pix: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="X pixel coordinate in reference frame"
    )
    y_pix: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Y pixel coordinate in reference frame"
    )

    # Flag e classificazione
    is_valid: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="False for FRACTION_OF_FAINTEST/BRIGHTEST rows"
    )
    is_known_variable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True if matched in VSX or Gaia variability catalog"
    )
    variable_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Variable type from VSX Type or Gaia variability flags"
    )
    catalog_matches: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Comma-separated catalog names: Gaia,AAVSO,Atlas"
    )
    vmag: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Calculated V magnitude from Gaia Gmag+BP-RP"
    )
    candidate_flag: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Candidate details from vast_autocandidates_details.log"
    )

    # Cross-match cataloghi
    gaia_match: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Match Gaia: {source_id, parallax, magnitude, ...}"
    )
    vsx_match: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Match VSX: {type, period, amplitude, ...}"
    )
    atlas_match: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Match ATLAS: {mag, error, ...}"
    )

    # Link a Project (opzionale)
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="SET NULL"),
        nullable=True,
        comment="Project AGATA associato"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False,
        comment="Data creazione risultato"
    )

    # Relationships
    job: Mapped["VastJob"] = relationship(
        "VastJob",
        back_populates="results",
        foreign_keys=[job_id]
    )
    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="joined"
    )

    def __repr__(self):
        return f"<VastResult(id={self.id}, job_id={self.job_id}, ra={self.ra}, dec={self.decl})>"

    @property
    def is_variable(self) -> bool:
        """True se il candidato ha indici di variabilità significativi o è una variabile nota."""
        if self.is_known_variable:
            return True
        if self.variability_index is None:
            return False
        return self.variability_index > 0.05
