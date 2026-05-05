import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Float, Numeric,
    Time, DateTime, ARRAY, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.enums import sentimen_enum, status_enum, wilayah_enum
 
 
class Nongkrong(Base):
    __tablename__ = "nongkrong"
 
    id                   = Column(Integer, primary_key=True, autoincrement=True)
    uid                  = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True, default=uuid.uuid4)
    kode                 = Column(String(20), nullable=False, unique=True, index=True)
    id_wisata_ref        = Column(String(20), ForeignKey("wisata.kode", ondelete="SET NULL"))
    nama                 = Column(String(255), nullable=False)
    wilayah              = Column(wilayah_enum, nullable=False)
    kecamatan            = Column(String(100))
    alamat_lengkap       = Column(Text)
    latitude             = Column(Float)
    longitude            = Column(Float)
    konsep_suasana       = Column(String(255))
    target_pengunjung    = Column(String(100))
    cocok_untuk          = Column(String(255))
    menu_best_seller     = Column(Text)
    harga_menu_min       = Column(Integer, default=0)
    harga_menu_max       = Column(Integer, default=0)
    jam_buka             = Column(Time)
    jam_tutup            = Column(Time)
    kapasitas_orang      = Column(Integer)
    fasilitas            = Column(ARRAY(String))
    batas_waktu_duduk    = Column(String(100))
    rating_google        = Column(Numeric(3, 1))
    minimal_order        = Column(Integer, default=0)
    link_google_maps     = Column(Text)
    kontak               = Column(String(50))
    gambar               = Column(ARRAY(String))
    sumber_data          = Column(String(100))
    catatan              = Column(Text)
    status               = Column(status_enum, nullable=False, default="draft")
    sentimen             = Column(sentimen_enum)
    skor_sentimen        = Column(Numeric(5, 4))
    total_ulasan_scraped = Column(Integer, default=0)
    total_positif        = Column(Integer, default=0)
    total_negatif        = Column(Integer, default=0)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    def __repr__(self):
        return f"<Nongkrong uid={self.uid} kode={self.kode} nama={self.nama}>"
