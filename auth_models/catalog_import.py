# agata/auth_models/catalog_import.py
"""
CatalogImport model - Tracciamento importazioni da cataloghi esterni

Gestisce il workflow di importazione dati fotometrici da:
- TESS (MAST)
- ZTF (IRSA)
- ASAS-SN
- OGLE
"""
from sqlalchemy import String, Integer, Float, Double, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class CatalogImport(Base):
    """
    Traccia le sessioni di importazione da cataloghi esterni.

    Workflow:
    1. Superuser/admin cerca stella (pending -> searching)
    2. Sistema interroga cataloghi (searching -> preview)
    3. Preview risultati disponibili
    4. Import selettivo (preview -> importing -> completed)
    5. Creazione Project opzionale (link project_id)
    """
    __tablename__ = "agata_catalog_imports"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Parametri ricerca
    search_type: Mapped[str] = mapped_column(
        SQLEnum('coordinates', 'gaia_id', 'name', 'file', name='catalog_search_type'),
        nullable=False,
        comment="Tipo ricerca: coordinates (RA/Dec), gaia_id, name (Simbad resolve), file (upload)"
    )
    search_value: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Valore ricerca (coordinate 'ra,dec' o identificativo)"
    )
    search_radius_arcsec: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=5.0,
        comment="Raggio ricerca in arcsec (per ricerca per coordinate)"
    )

    # Coordinate risolte
    resolved_ra: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Right Ascension risolta (gradi)"
    )
    resolved_dec: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Declination risolta (gradi)"
    )
    resolved_gaia_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Gaia DR3 source ID risolto"
    )

    # Risultati ricerca per catalogo
    catalogs_queried: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Risultati per catalogo: {catalog: {status, count, error, band, time_range}}"
    )

    # Contatori punti
    total_points_available: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Totale punti fotometrici disponibili"
    )
    total_points_imported: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Totale punti importati in Cataloghi_esterni"
    )

    # Selezione utente
    selected_catalogs: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Cataloghi selezionati per import: ['TESS', 'ZTF', ...]"
    )

    # Stato importazione
    state: Mapped[str] = mapped_column(
        SQLEnum('pending', 'searching', 'preview', 'importing', 'completed', 'failed', 'cancelled',
                name='catalog_import_state'),
        default='pending',
        nullable=False,
        comment="Stato corrente del workflow di importazione"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Messaggio errore in caso di fallimento"
    )

    # Utente richiedente
    requested_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID che ha richiesto l'importazione"
    )

    # Link a Project creato (opzionale)
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="SET NULL"),
        nullable=True,
        comment="Project AGATA creato da questa importazione"
    )

    # Associazione target per il Project
    target_association_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_associations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Associazione a cui assegnare il Project"
    )

    # Note
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Note sull'importazione"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False,
        comment="Data creazione richiesta"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Data completamento importazione"
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
    target_association: Mapped["Association"] = relationship(
        "Association",
        foreign_keys=[target_association_id],
        lazy="joined"
    )

    def __repr__(self):
        return f"<CatalogImport(id={self.id}, search='{self.search_value}', state='{self.state}')>"

    @property
    def catalogs_with_data(self) -> list:
        """Restituisce lista cataloghi con dati disponibili."""
        if not self.catalogs_queried:
            return []
        return [
            name for name, info in self.catalogs_queried.items()
            if info.get('status') == 'success' and info.get('count', 0) > 0
        ]

    @property
    def is_importable(self) -> bool:
        """True se ci sono dati da importare e lo stato lo permette."""
        return self.state == 'preview' and self.total_points_available > 0

    @property
    def can_create_project(self) -> bool:
        """True se l'import e' completato e non ha gia' un project."""
        return self.state == 'completed' and self.project_id is None
