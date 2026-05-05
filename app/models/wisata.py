import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, Numeric,
    Time, DateTime, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.enums import kategori_wisata_enum, sentimen_enum, status_enum, wilayah_enum
 
 
class Wisata(Base):
    __tablename__ = "wisata"
 
    id                      = Column(Integer, primary_key=True, autoincrement=True)
    uid                     = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True, default=uuid.uuid4)
    kode                    = Column(String(20), nullable=False, unique=True, index=True)
    nama                    = Column(String(255), nullable=False)
    wilayah                 = Column(wilayah_enum, nullable=False)
    kecamatan               = Column(String(100))
    alamat_lengkap          = Column(Text)
    latitude                = Column(Float)
    longitude               = Column(Float)
    kategori_utama          = Column(kategori_wisata_enum)
    sub_kategori            = Column(String(100))
    jenis_tempat            = Column(String(100))
    deskripsi               = Column(Text)
    harga_tiket_min         = Column(Integer, default=0)
    harga_tiket_max         = Column(Integer, default=0)
    gratis                  = Column(Boolean, default=False)
    jam_buka                = Column(Time)
    jam_tutup               = Column(Time)
    hari_libur_operasional  = Column(String(255))
    estimasi_durasi_jam     = Column(Numeric(4, 1))
    fasilitas               = Column(ARRAY(String))
    aksesibilitas           = Column(String(100))
    moda_transportasi       = Column(String(255))
    rating_google           = Column(Numeric(3, 1))
    jumlah_ulasan_google    = Column(Integer, default=0)
    link_google_maps        = Column(Text)
    link_instagram          = Column(Text)
    link_website            = Column(Text)
    kontak                  = Column(String(50))
    gambar                  = Column(ARRAY(String))
    sumber_data             = Column(String(100))
    diinput_oleh            = Column(String(100))
    status                  = Column(status_enum, nullable=False, default="draft")
    # Kolom AI — diisi otomatis sistem
    sentimen                = Column(sentimen_enum)
    skor_sentimen           = Column(Numeric(5, 4))
    total_ulasan_scraped    = Column(Integer, default=0)
    total_positif           = Column(Integer, default=0)
    total_negatif           = Column(Integer, default=0)
    created_at              = Column(DateTime(timezone=True), server_default=func.now())
    updated_at              = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    def __repr__(self):
        return f"<Wisata uid={self.uid} kode={self.kode} nama={self.nama}>"
