# agata/auth_models/catalog_attribute.py
"""
CatalogAttribute model - Persistent cache di attributi da cataloghi esterni

Salva gli attributi interrogati da cataloghi Vizier, permettendo accesso veloce
senza ripetere le query a Vizier per la stessa stella e catalogo.

Workflow:
1. User interroga cataloghi per stella X con Gaia ID Y
2. QueryService controlla DB: SELECT ... WHERE gaia_id='Y' AND catalog_id='Z'
3. Se trovato e non scaduto: restituisce valore (cache hit)
4. Se non trovato: query Vizier, salva risultato filtrato in DB
5. Successive query per stessa stella: cache hit, veloce
"""
from sqlalchemy import String, Integer, Float, Double, ForeignKey, Text, JSON, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timedelta
from agata.models import Base


class CatalogAttribute(Base):
    """
    Persistent cache di singolo attributo da catalogo esterno.

    Chiave composita: (gaia_id, catalog_id, attribute_name)
    Permette di recuperare velocemente attributi senza query a Vizier.
    """
    __tablename__ = "agata_catalog_attributes"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Chiave composita (gaia_id, catalog_id, attribute_name)
    gaia_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Gaia DR3 source ID della stella"
    )
    catalog_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Identificativo catalogo (es: I/305/out, I/255/out)"
    )
    attribute_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Nome attributo (es: GSC2.3, USNO_A2_0)"
    )

    # Metadati del catalogo (da CSV)
    contesto: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Contesto catalogo: identificativi, parametri_fisici, magnitudine, tipo_spettrale, variabilita_nota"
    )
    reference: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Reference bibliografico da CSV (es: '2023ApJ...950..32X')"
    )

    # Valore attributo
    value: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Valore attributo come stringa (supporta numeri, stringhe, identificativi)"
    )
    value_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Tipo valore: string, float, int, identifier"
    )

    # Coordinate stella (per debug e validazione)
    ra_deg: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Right Ascension stella (gradi)"
    )
    dec_deg: Mapped[float | None] = mapped_column(
        Double, nullable=True,
        comment="Declination stella (gradi)"
    )

    # Distanza dal match (per valutare qualità del match)
    distance_arcsec: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Distanza angolare tra coordinate stella e match Vizier (arcsec)"
    )

    # Timestamp
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
        comment="Data/ora interrogazione Vizier"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="Data/ora scadenza cache (NULL = non scade)"
    )

    def __repr__(self):
        return f"<CatalogAttribute(gaia_id={self.gaia_id}, catalog={self.catalog_id}, attr={self.attribute_name})>"

    @property
    def is_expired(self) -> bool:
        """True se l'entry è scaduta."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def age_days(self) -> float:
        """Giorni dalla interrogazione."""
        return (datetime.utcnow() - self.fetched_at).total_seconds() / 86400

    def set_expiry(self, days: int = 180):
        """Imposta scadenza a N giorni da ora (default 180 = 6 mesi)."""
        self.expires_at = datetime.utcnow() + timedelta(days=days)

    def invalidate(self):
        """Marca come scaduto (forza refetch da Vizier)."""
        self.expires_at = datetime.utcnow()
