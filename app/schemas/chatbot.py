from typing import List, Optional
from pydantic import BaseModel, field_validator
 
 
class ChatRequest(BaseModel):
    message:       str
    session_token: Optional[str]   = None
    latitude:      Optional[float] = None
    longitude:     Optional[float] = None
    debug:         Optional[bool]   = False
 
    @field_validator("message")
    @classmethod
    def message_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pesan tidak boleh kosong")
        if len(v) > 1000:
            raise ValueError("Pesan maksimal 1000 karakter")
        return v
 
    @field_validator("latitude")
    @classmethod
    def lat_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("Latitude harus antara -90 dan 90")
        return v
 
    @field_validator("longitude")
    @classmethod
    def lon_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("Longitude harus antara -180 dan 180")
        return v
 
 
class ChatMessage(BaseModel):
    role:      str
    content:   str
    timestamp: str
 
 
class ChatReferensi(BaseModel):
    nama:      str
    tipe:      str
    wilayah:   str
    link_maps: Optional[str] = None
 
 
class ChatResponse(BaseModel):
    session_token:      str
    answer:             str
    wilayah_terdeteksi: Optional[str]        = None
    referensi:          List[ChatReferensi]  = []
    messages_count:     int                  = 0
    # Optional debug output (only present when client requests debug=True)
    retrieved_docs:     Optional[List[dict]] = None
 
 
class ChatHistoryResponse(BaseModel):
    session_token:      str
    messages:           List[ChatMessage]
    wilayah_terdeteksi: Optional[str] = None
    created_at:         str