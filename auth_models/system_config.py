# agata/auth_models/system_config.py
from sqlalchemy import String, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from agata.models import Base


class SystemConfig(Base):
    __tablename__ = "agata_system_config"

    config_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    config_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_type: Mapped[str] = mapped_column(
        SQLEnum('string', 'integer', 'boolean', 'json', name='config_type'),
        default='string'
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("agata_users.id", ondelete="SET NULL"), nullable=True)
