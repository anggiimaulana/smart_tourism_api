from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator
from app.schemas.wisata import WilayahEnum
 
 
class RecommendationRequest(BaseModel):
    user_id:   Optional[str]            = None
    latitude:  Optional[float]          = None
    longitude: Optional[float]          = None
    wilayah:   Optional[List[WilayahEnum]] = None
    kategori:  Optional[List[str]]      = None
    budget_max: Optional[int]           = None
    tipe:      Literal["wisata","kuliner","nongkrong","all"] = "all"
    jumlah:    int                       = 10
    mode:      Literal["personal","popular","nearby"]        = "personal"
 
    @field_validator("jumlah")
    @classmethod
    def jumlah_range(cls, v: int) -> int:
        if not (1 <= v <= 20):
            raise ValueError("Jumlah rekomendasi harus antara 1–20")
        return v
 
 
class PlanningRequest(BaseModel):
    user_id:          Optional[str]            = None
    wilayah:          List[WilayahEnum]
    jumlah_hari:      int
    jumlah_orang:     int                       = 1
    budget_total:     Optional[int]             = None
    preferensi:       Optional[List[str]]       = None
    tanggal_mulai:    Optional[str]             = None   # YYYY-MM-DD
    catatan_tambahan: Optional[str]             = None
 
    @field_validator("jumlah_hari")
    @classmethod
    def hari_range(cls, v: int) -> int:
        if not (1 <= v <= 14):
            raise ValueError("Jumlah hari harus antara 1–14")
        return v
 
    @field_validator("wilayah")
    @classmethod
    def wilayah_not_empty(cls, v: List) -> List:
        if not v:
            raise ValueError("Pilih minimal 1 wilayah")
        return v
 
 
class RecommendedItem(BaseModel):
    id:               int
    kode:             str
    nama:             str
    tipe:             str
    wilayah:          str
    kecamatan:        Optional[str]   = None
    alamat:           Optional[str]   = None
    latitude:         Optional[float] = None
    longitude:        Optional[float] = None
    deskripsi:        Optional[str]   = None
    gambar:           List[str]       = []
    rating_google:    Optional[float] = None
    harga_min:        int             = 0
    harga_max:        int             = 0
    sentimen:         Optional[str]   = None
    skor_sentimen:    Optional[float] = None
    link_google_maps: Optional[str]   = None
    skor_rekomendasi: float           = 0.0
 
 
class RecommendationResponse(BaseModel):
    mode:  str
    total: int
    items: List[RecommendedItem]
 
 
class PlanningDayItem(BaseModel):
    hari:    int
    tanggal: Optional[str]
    items:   List[RecommendedItem]
 
 
class PlanningResponse(BaseModel):
    judul:             str
    wilayah:           List[str]
    jumlah_hari:       int
    estimasi_budget:   Optional[int]
    hari:              List[PlanningDayItem]
 
 
class TrackHistoryRequest(BaseModel):
    user_id:     str
    tipe_tempat: Literal["wisata","kuliner","nongkrong"]
    tempat_kode: str
    aksi:        Literal["klik","kunjungi","simpan","rating","share"]
    nilai_rating: Optional[float] = None
    durasi_detik: Optional[int]   = None
 
    @field_validator("nilai_rating")
    @classmethod
    def rating_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (1.0 <= v <= 5.0):
            raise ValueError("Rating harus antara 1.0–5.0")
        return v