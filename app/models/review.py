from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base  

class Review(Base):
    __tablename__ = "reviews"

    # id menggunakan tipe data UUID, otomatis digenerate lewat server PostgreSQL (uuid_generate_v4())
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    
    # Berrelasi langsung dengan tabel 'users' di proyekmu (01_schema.sql)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Berrelasi secara logis dengan id tempat di view 'v_all_tempat' (03_fts.sql)
    tempat_id = Column(UUID(as_uuid=True), nullable=False) 
    
    # Rating dibatasi skala 1-5
    rating = Column(Integer, nullable=False)
    
    # Komentar/ulasan teks opsional (bisa kosong)
    comment = Column(Text, nullable=True)
    
    # Timestamp otomatis
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))