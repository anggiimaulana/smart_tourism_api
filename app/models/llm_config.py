from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class LlmConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)
    base_url = Column(Text, nullable=True)
    api_key = Column(Text, nullable=True)
    model = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
