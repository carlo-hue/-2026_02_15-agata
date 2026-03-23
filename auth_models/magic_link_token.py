# agata/auth_models/magic_link_token.py
"""
MagicLinkToken model - Token per autenticazione via Magic Link

Permette login senza password: l'utente riceve un link via email
che contiene un token monouso con scadenza.
"""
from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timedelta
from agata.models import Base
import secrets


class MagicLinkToken(Base):
    """
    Token per Magic Link authentication

    - Token generato con secrets.token_urlsafe (32 bytes)
    - Scadenza configurabile (default 15 minuti)
    - Monouso: invalidato dopo primo utilizzo
    """
    __tablename__ = "agata_magic_link_tokens"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Token (URL-safe, 43 caratteri)
    token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False,
                                        index=True, comment="Token URL-safe")

    # Email destinatario (non necessariamente utente esistente)
    email: Mapped[str] = mapped_column(String(255), nullable=False,
                                        index=True, comment="Email destinatario")

    # Utente associato (NULL se nuovo utente)
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="CASCADE"),
        nullable=True,
        comment="ID utente esistente (NULL per nuovi utenti)"
    )

    # Stato token
    is_used: Mapped[bool] = mapped_column(Boolean, default=False,
                                           comment="TRUE se già utilizzato")

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                  nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                  comment="Scadenza token")
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True,
                                                      comment="Quando è stato utilizzato")

    # IP tracking
    created_ip: Mapped[str | None] = mapped_column(String(45), nullable=True,
                                                    comment="IP richiesta creazione")
    used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True,
                                                 comment="IP utilizzo token")

    # Relationship
    user: Mapped["User"] = relationship("User", backref="magic_link_tokens")

    def __repr__(self):
        return f"<MagicLinkToken(id={self.id}, email='{self.email}', used={self.is_used})>"

    @classmethod
    def generate(cls, email: str, user_id: str | None = None,
                 expires_minutes: int = 15, ip_address: str | None = None) -> "MagicLinkToken":
        """
        Genera un nuovo token magic link

        Args:
            email: Email destinatario
            user_id: ID utente esistente (opzionale)
            expires_minutes: Minuti validità (default 15)
            ip_address: IP richiedente

        Returns:
            Nuova istanza MagicLinkToken
        """
        return cls(
            token=secrets.token_urlsafe(32),
            email=email.lower().strip(),
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes),
            created_ip=ip_address,
        )

    @property
    def is_valid(self) -> bool:
        """Check se token è ancora valido (non usato e non scaduto)"""
        if self.is_used:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    def mark_used(self, ip_address: str | None = None) -> None:
        """Marca token come utilizzato"""
        self.is_used = True
        self.used_at = datetime.utcnow()
        self.used_ip = ip_address
