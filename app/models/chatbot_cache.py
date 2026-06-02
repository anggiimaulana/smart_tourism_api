import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class ChatbotCache(Base):
    __tablename__ = "chatbot_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_token = Column(String(255), nullable=True) # Tambahkan session_token
    query_hash = Column(String(128), index=True, nullable=False) # Hilangkan unique=True dari sini
    query_normalized = Column(Text, nullable=False)
    answer = Column(JSONB, nullable=False)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Tambahkan composite unique constraint (session_token, query_hash)
    from sqlalchemy import UniqueConstraint
    __table_args__ = (
        UniqueConstraint('session_token', 'query_hash', name='uq_session_query_hash'),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ChatbotCache {self.query_hash[:12]}... hits={self.hit_count}>"
