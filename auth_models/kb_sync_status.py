"""
Knowledge Base Sync Status Model
"""
from agata.models import Base
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship


class KBSyncStatus(Base):
    """Track knowledge base synchronization status for different sources"""

    __tablename__ = 'agata_kb_sync_status'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)  # 'gmail', 'teams', 'drive', 'mbox'
    user_id = Column(String(36), ForeignKey('agata_users.id'), nullable=True)
    association_id = Column(Integer, ForeignKey('agata_associations.id'), nullable=True)

    last_sync_at = Column(DateTime, nullable=True)
    total_items_indexed = Column(Integer, default=0, nullable=False)
    items_added_last_sync = Column(Integer, default=0, nullable=False)

    sync_status = Column(
        Enum('never_synced', 'syncing', 'completed', 'error', name='kb_sync_status_enum'),
        default='never_synced',
        nullable=False
    )
    error_message = Column(Text, nullable=True)

    config = Column(JSON, nullable=True)  # Source-specific config (labels, channels, etc.)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user = relationship('User', backref='kb_sync_statuses')
    association = relationship('Association', backref='kb_sync_statuses')

    # Unique constraint: one sync status per source + user + association
    __table_args__ = (
        UniqueConstraint('source', 'user_id', 'association_id', name='uq_source_user_assoc'),
    )

    def __repr__(self):
        return f"<KBSyncStatus {self.source} - {self.sync_status}>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'source': self.source,
            'user_id': self.user_id,
            'association_id': self.association_id,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'total_items_indexed': self.total_items_indexed,
            'items_added_last_sync': self.items_added_last_sync,
            'sync_status': self.sync_status,
            'error_message': self.error_message,
            'config': self.config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
