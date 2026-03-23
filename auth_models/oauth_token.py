# agata/auth_models/oauth_token.py
"""
OAuth Token model - Token OAuth per integrazioni servizi esterni
"""
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from agata.models import Base


class OAuthToken(Base):
    """
    Token OAuth 2.0 per integrazione con servizi esterni

    Memorizza access_token e refresh_token per:
    - Google (accesso API Google)
    - Slack (invio messaggi, gestione canali)
    - GitHub (opzionale)
    """
    __tablename__ = "agata_oauth_tokens"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Riferimento utente
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agata_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Riferimento utente"
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False,
                                          comment="Provider OAuth")

    # Token OAuth 2.0
    access_token: Mapped[str] = mapped_column(Text, nullable=False,
                                              comment="Access token per API calls")
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                       comment="Refresh token per rinnovo")
    token_type: Mapped[str] = mapped_column(String(50), default='Bearer',
                                            comment="Tipo token")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True,
                                                         comment="Scadenza access token")
    scope: Mapped[str | None] = mapped_column(Text, nullable=True,
                                              comment="Scope autorizzati (spazio-separati)")

    # Metadati
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="oauth_tokens")

    def __repr__(self):
        return f"<OAuthToken(id={self.id}, user_id='{self.user_id}', provider='{self.provider}')>"

    @property
    def is_expired(self) -> bool:
        """Check se il token è scaduto"""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at

    def needs_refresh(self, buffer_seconds: int = 300) -> bool:
        """
        Check se il token deve essere rinnovato

        Args:
            buffer_seconds: Secondi prima della scadenza per considerare il rinnovo

        Returns:
            True se mancano meno di buffer_seconds alla scadenza
        """
        if not self.expires_at:
            return False

        buffer_time = datetime.utcnow().timestamp() + buffer_seconds
        return self.expires_at.timestamp() <= buffer_time
