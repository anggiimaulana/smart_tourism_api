import uuid
from sqlalchemy import Column, String, Boolean, Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import DateTime
 
from app.core.database import Base
 
 
class User(Base):
    __tablename__ = "users"
 
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nama          = Column(String(150), nullable=False)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role          = Column(PgEnum("admin", "pengunjung", name="role_enum"),
                           nullable=False, default="pengunjung")
    avatar_url    = Column(String)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    def __repr__(self):
        return f"<User id={self.id} email={self.email} role={self.role}>"