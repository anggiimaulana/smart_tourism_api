from typing import List, Optional
from pydantic import BaseModel, field_validator, ConfigDict
from app.schemas.wisata import WilayahEnum, SentimenEnum, StatusEnum
 
 
class NongkrongBase(BaseModel):
    nama:              str
    wilayah:           WilayahEnum
    kecamatan:         Optional[str]   = None
    alamat_lengkap:    Optional[str]   = None
    latitude:          Optional[float] = None
    longitude:         Optional[float] = None
    id_wisata_ref:     Optional[str]   = None
    konsep_suasana:    Optional[str]   = None
    target_pengunjung: Optional[str]   = None
    cocok_untuk:       Optional[str]   = None
    menu_best_seller:  Optional[str]   = None
    harga_menu_min:    int             = 0
    harga_menu_max:    int             = 0
    jam_buka:          Optional[str]   = None
    jam_tutup:         Optional[str]   = None
    kapasitas_orang:   Optional[int]   = None
    fasilitas:         List[str]       = []
    batas_waktu_duduk: Optional[str]   = None
    rating_google:     Optional[float] = None
    minimal_order:     int             = 0
    link_google_maps:  Optional[str]   = None
    kontak:            Optional[str]   = None
    gambar:            List[str]       = []
    catatan:           Optional[str]   = None
    status:            StatusEnum      = StatusEnum.draft
 
    @field_validator("nama")
    @classmethod
    def nama_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Nama tempat nongkrong tidak boleh kosong")
        return v.strip()
 
 
class NongkrongCreate(NongkrongBase):
    pass
 
 
class NongkrongUpdate(BaseModel):
    nama:              Optional[str]       = None
    konsep_suasana:    Optional[str]       = None
    menu_best_seller:  Optional[str]       = None
    harga_menu_min:    Optional[int]       = None
    harga_menu_max:    Optional[int]       = None
    fasilitas:         Optional[List[str]] = None
    gambar:            Optional[List[str]] = None
    status:            Optional[StatusEnum] = None
 
 
class NongkrongResponse(NongkrongBase):
    id:                   int
    kode:                 str
    sentimen:             Optional[SentimenEnum] = None
    skor_sentimen:        Optional[float]        = None
    total_ulasan_scraped: int = 0
    total_positif:        int = 0
    total_negatif:        int = 0
 
    @field_validator("gambar", mode="after")
    @classmethod
    def prepend_base_url(cls, v: List[str]) -> List[str]:
        from app.core.config import settings
        result = []
        for img in v:
            if img and not str(img).startswith("http"):
                result.append(f"{settings.LARAVEL_URL.rstrip('/')}/storage/{img}")
            else:
                result.append(str(img))
        return result
 
    model_config = ConfigDict(from_attributes=True)
 