from typing import List, Optional
from pydantic import BaseModel, field_validator
from enum import Enum
 
 
class WilayahEnum(str, Enum):
    indramayu  = "Indramayu"
    cirebon    = "Cirebon"
    majalengka = "Majalengka"
    kuningan   = "Kuningan"
 
 
class SentimenEnum(str, Enum):
    positif = "positif"
    negatif = "negatif"
    netral  = "netral"
 
 
class StatusEnum(str, Enum):
    aktif    = "aktif"
    nonaktif = "nonaktif"
    draft    = "draft"
 
 
class WisataBase(BaseModel):
    nama:                  str
    wilayah:               WilayahEnum
    kecamatan:             Optional[str]   = None
    alamat_lengkap:        Optional[str]   = None
    latitude:              Optional[float] = None
    longitude:             Optional[float] = None
    kategori_utama:        Optional[str]   = None
    sub_kategori:          Optional[str]   = None
    jenis_tempat:          Optional[str]   = None
    deskripsi:             Optional[str]   = None
    harga_tiket_min:       int             = 0
    harga_tiket_max:       int             = 0
    gratis:                bool            = False
    jam_buka:              Optional[str]   = None   # "HH:MM"
    jam_tutup:             Optional[str]   = None
    hari_libur_operasional: Optional[str]  = None
    estimasi_durasi_jam:   Optional[float] = None
    fasilitas:             List[str]       = []
    aksesibilitas:         Optional[str]   = None
    moda_transportasi:     Optional[str]   = None
    rating_google:         Optional[float] = None
    jumlah_ulasan_google:  int             = 0
    link_google_maps:      Optional[str]   = None
    link_instagram:        Optional[str]   = None
    link_website:          Optional[str]   = None
    kontak:                Optional[str]   = None
    gambar:                List[str]       = []
    sumber_data:           Optional[str]   = None
    status:                StatusEnum      = StatusEnum.draft
 
    @field_validator("nama")
    @classmethod
    def nama_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Nama wisata tidak boleh kosong")
        return v.strip()
 
    @field_validator("rating_google")
    @classmethod
    def rating_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 5.0):
            raise ValueError("Rating harus antara 0.0–5.0")
        return v
 
    @field_validator("harga_tiket_min", "harga_tiket_max")
    @classmethod
    def harga_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Harga tidak boleh negatif")
        return v
 
 
class WisataCreate(WisataBase):
    """Payload untuk POST /wisata/ — semua field wajib kecuali Optional."""
    pass
 
 
class WisataUpdate(BaseModel):
    """Payload untuk PATCH /wisata/{kode} — semua field opsional."""
    nama:              Optional[str]       = None
    kecamatan:         Optional[str]       = None
    deskripsi:         Optional[str]       = None
    harga_tiket_min:   Optional[int]       = None
    harga_tiket_max:   Optional[int]       = None
    gratis:            Optional[bool]      = None
    jam_buka:          Optional[str]       = None
    jam_tutup:         Optional[str]       = None
    fasilitas:         Optional[List[str]] = None
    gambar:            Optional[List[str]] = None
    link_google_maps:  Optional[str]       = None
    rating_google:     Optional[float]     = None
    status:            Optional[StatusEnum] = None
 
 
class WisataResponse(WisataBase):
    """Response satu wisata — termasuk kolom AI yang diisi sistem."""
    id:                   int
    kode:                 str
    sentimen:             Optional[SentimenEnum] = None
    skor_sentimen:        Optional[float]        = None
    total_ulasan_scraped: int                    = 0
    total_positif:        int                    = 0
    total_negatif:        int                    = 0
 
    model_config = {"from_attributes": True}
 
 
class WisataListResponse(BaseModel):
    items:       List[WisataResponse]
    total:       int
    page:        int
    limit:       int
    total_pages: int