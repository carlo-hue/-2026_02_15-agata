"""
Knowledge Base Search History Model - Track user searches for analytics
"""
from agata.models import Base
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Integer, Text, ForeignKey, DateTime, Index
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship


class KBSearchHistory(Base):
    """Track user searches in the knowledge base for analytics and improvement"""

    __tablename__ = 'agata_kb_search_history'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey('agata_users.id'), nullable=True)

    query = Column(Text, nullable=False)  # User's search query
    results_count = Column(Integer, default=0, nullable=False)  # Number of results returned

    sources_used = Column(JSON, nullable=True)  # ['gmail', 'teams', 'drive']
    clicked_result_id = Column(String(255), nullable=True)  # Which result user clicked

    search_duration_ms = Column(Integer, nullable=True)  # How long search took

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship('User', backref='kb_searches')

    # Indexes
    __table_args__ = (
        Index('idx_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<KBSearchHistory '{self.query[:50]}...' by {self.user_id}>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'query': self.query,
            'results_count': self.results_count,
            'sources_used': self.sources_used,
            'clicked_result_id': self.clicked_result_id,
            'search_duration_ms': self.search_duration_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
