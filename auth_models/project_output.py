# agata/auth_models/project_output.py
"""
Project Output model - Output scientifici con versioning leggero
"""
from sqlalchemy import String, Integer, BigInteger, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class ProjectOutput(Base):
    """
    Output scientifici per progetti AGATA con versioning leggero

    Supporta immagini, fit, report, lightcurve, periodogrammi, phase plots
    con tracking delle versioni per modifiche iterative
    """
    __tablename__ = "agata_project_outputs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK -> agata_projects"
    )

    # ========================================================================
    # TIPO E RIFERIMENTO FILE
    # ========================================================================
    output_type: Mapped[str] = mapped_column(
        SQLEnum('image', 'fit', 'report', 'lightcurve', 'periodogram', 'phase_plot', 'other',
                name='project_output_type'),
        nullable=False,
        comment="Tipo output: image/fit/report/lightcurve/periodogram/phase_plot/other"
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Nome file originale"
    )
    file_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="URL completo file (Google Drive, S3, storage interno, etc.)"
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Dimensione file in bytes"
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="MIME type (image/png, application/pdf, text/csv, etc.)"
    )

    # ========================================================================
    # DESCRIZIONE E METADATI
    # ========================================================================
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Descrizione output (cosa rappresenta, contesto)"
    )
    tags: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Tag comma-separated per ricerca/filtro (es: final, draft, v2, test)"
    )

    # ========================================================================
    # VERSIONING LEGGERO
    # ========================================================================
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Versione output (incrementa per modifiche successive)"
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="TRUE se è la versione corrente/attiva mostrata in UI"
    )
    replaces_output_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_project_outputs.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK -> agata_project_outputs (ID output che questa versione sostituisce)"
    )

    # ========================================================================
    # AUDIT
    # ========================================================================
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK -> agata_users chi ha caricato questo output"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        comment="Data/ora caricamento"
    )

    # Relationships
    # project: Mapped["Project"] = relationship("Project", back_populates="outputs")
    # uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by])
    # replaces: Mapped["ProjectOutput"] = relationship("ProjectOutput", remote_side=[id])

    def __repr__(self):
        return (f"<ProjectOutput(id={self.id}, project_id={self.project_id}, "
                f"type='{self.output_type}', version={self.version}, "
                f"current={self.is_current})>")

    def get_file_extension(self) -> str:
        """Estrae l'estensione dal nome file"""
        if '.' in self.file_name:
            return self.file_name.rsplit('.', 1)[1].lower()
        return ''

    def is_image(self) -> bool:
        """Verifica se output è un'immagine"""
        image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
        return (self.output_type == 'image' or
                self.get_file_extension() in image_extensions)

    def is_document(self) -> bool:
        """Verifica se output è un documento"""
        doc_extensions = {'pdf', 'doc', 'docx', 'txt', 'md'}
        return (self.output_type == 'report' or
                self.get_file_extension() in doc_extensions)
