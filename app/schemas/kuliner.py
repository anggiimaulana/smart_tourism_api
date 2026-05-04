from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.schemas.wisata import WilayahEnum, SentimenEnum, StatusEnum
 
 
class KulinerBase(BaseModel):
    nama:                str
    wilayah:             WilayahEnum
    kecamatan:           Optional[str]   = None
    alamat_lengkap:      Optional[str]   = None
    latitude:            Optional[float] = None
    longitude:           Optional[float] = None
    id_wisata_terdekat:  Optional[str]   = None
    jenis_tempat:        Optional[str]   = None
    kategori_menu_utama: Optional[str]   = None
    menu_unggulan:       Optional[str]   = None
    makanan_khas_daerah: bool            = False
    nama_makanan_khas:   Optional[str]   = None
    harga_menu_min:      int             = 0
    harga_menu_max:      int             = 0
    jam_buka:            Optional[str]   = None
    jam_tutup:           Optional[str]   = None
    kapasitas_orang:     Optional[int]   = None
    fasilitas:           List[str]       = []
    sertifikat_halal:    bool            = False
    rating_google:       Optional[float] = None
    jumlah_ulasan_google: int            = 0
    link_google_maps:    Optional[str]   = None
    kontak:              Optional[str]   = None
    gambar:              List[str]       = []
    catatan:             Optional[str]   = None
    status:              StatusEnum      = StatusEnum.draft
 
    @field_validator("nama")
    @classmethod
    def nama_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Nama kuliner tidak boleh kosong")
        return v.strip()
 
 
class KulinerCreate(KulinerBase):
    pass
 
 
class KulinerUpdate(BaseModel):
    nama:              Optional[str]       = None
    menu_unggulan:     Optional[str]       = None
    harga_menu_min:    Optional[int]       = None
    harga_menu_max:    Optional[int]       = None
    fasilitas:         Optional[List[str]] = None
    gambar:            Optional[List[str]] = None
    sertifikat_halal:  Optional[bool]      = None
    status:            Optional[StatusEnum] = None
 
 
class KulinerResponse(KulinerBase):
    id:                   int
    kode:                 str
    sentimen:             Optional[SentimenEnum] = None
    skor_sentimen:        Optional[float]        = None
    total_ulasan_scraped: int = 0
    total_positif:        int = 0
    total_negatif:        int = 0
 
    model_config = {"from_attributes": True}