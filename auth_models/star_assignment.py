# agata/auth_models/star_assignment.py
"""
StarAssignment model - Assegnazione stelle a associazioni

Tabella intermedia che traccia quali stelle (dal bacino centrale)
sono state assegnate a quali associazioni, prima che diventino progetti.

Workflow:
1. Superuser carica stelle -> dati in Cataloghi_esterni (bacino centrale)
2. Superuser assegna stella a associazione -> record in star_assignments
3. Admin vede stelle assegnate -> crea progetto quando decide di lavorarci
"""
from sqlalchemy import String, Integer, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class StarAssignment(Base):
    """
    Assegnazione di una stella (Gaia ID) a un'associazione.

    Una stella può essere assegnata a più associazioni.
    Quando l'admin crea un progetto, l'assegnazione può rimanere
    (per tracciabilità) o essere rimossa.
    """
    __tablename__ = "agata_star_assignments"

    # Primary key composita: gaia_id + association_id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Gaia ID della stella (riferimento a Cataloghi_esterni.Source)
    gaia_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Gaia DR3 source ID"
    )

    # Associazione a cui è assegnata
    association_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agata_associations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Associazione destinataria"
    )

    # Chi ha fatto l'assegnazione (superuser)
    assigned_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID superuser che ha assegnato"
    )

    # Quando è stata fatta l'assegnazione
    assigned_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        comment="Data assegnazione"
    )

    # Note opzionali
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Note sull'assegnazione"
    )

    # Se è stato creato un progetto da questa assegnazione
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_projects.id", ondelete="SET NULL"),
        nullable=True,
        comment="Progetto creato da questa assegnazione (se esiste)"
    )

    # Relationships
    association: Mapped["Association"] = relationship(
        "Association",
        back_populates="star_assignments"
    )
    assigned_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[assigned_by]
    )
    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id]
    )

    # Indice unico: una stella può essere assegnata una sola volta a un'associazione
    __table_args__ = (
        Index('ix_star_assignment_unique', 'gaia_id', 'association_id', unique=True),
    )

    def __repr__(self):
        return f"<StarAssignment(gaia_id='{self.gaia_id}', association_id={self.association_id})>"
