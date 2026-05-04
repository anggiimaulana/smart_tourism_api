import uuid
from sqlalchemy import Column, String, Float, DateTime, Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base
 
 
class ChatbotSession(Base):
    __tablename__ = "chatbot_sessions"
 
    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id             = Column(UUID(as_uuid=True), index=True)
    session_token       = Column(String(100), nullable=False, unique=True, index=True)
    messages            = Column(JSONB, nullable=False, default=list)
    latitude            = Column(Float)
    longitude           = Column(Float)
    wilayah_terdeteksi  = Column(PgEnum("Indramayu","Cirebon","Majalengka","Kuningan",
                                       name="wilayah_enum"))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    def __repr__(self):
        return f"<ChatbotSession token={self.session_token[:12]}...>"