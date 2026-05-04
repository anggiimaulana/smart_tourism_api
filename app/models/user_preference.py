from sqlalchemy import Column, Integer, DateTime, ARRAY, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
 
 
class UserPreference(Base):
    __tablename__ = "user_preferences"
 
    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(UUID(as_uuid=True), nullable=False, unique=True)
    kategori_favorit = Column(ARRAY(String))
    wilayah_favorit  = Column(ARRAY(String))
    budget_min       = Column(Integer, default=0)
    budget_max       = Column(Integer, default=0)
    tipe_wisata      = Column(ARRAY(String))
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    def __repr__(self):
        return f"<UserPreference user={self.user_id}>"