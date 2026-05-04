from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator
 
 
class SentimentRequest(BaseModel):
    text:        str
    model:       Literal["indobert","naive_bayes","svm","decision_tree"] = "indobert"
    tipe_tempat: Literal["wisata","kuliner","nongkrong"]
    tempat_kode: str
 
    @field_validator("text")
    @classmethod
    def text_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Teks tidak boleh kosong")
        if len(v) < 5:
            raise ValueError("Teks minimal 5 karakter")
        if len(v) > 2000:
            raise ValueError("Teks maksimal 2000 karakter")
        return v
 
    @field_validator("tempat_kode")
    @classmethod
    def kode_valid(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Kode tempat tidak boleh kosong")
        return v.strip().upper()
 
 
class SentimentResponse(BaseModel):
    text:        str
    sentimen:    Literal["positif","negatif","netral"]
    confidence:  float
    model_used:  str
    tipe_tempat: str
    tempat_kode: str
 
 
class SentimentBatchRequest(BaseModel):
    items: List[SentimentRequest]
 
    @field_validator("items")
    @classmethod
    def items_valid(cls, v: List) -> List:
        if not v:
            raise ValueError("Batch tidak boleh kosong")
        if len(v) > 100:
            raise ValueError("Maksimal 100 item per batch")
        return v
 
 
class SentimentSummaryResponse(BaseModel):
    wilayah:        str
    tipe_tempat:    str
    total_ulasan:   int
    total_positif:  int
    total_negatif:  int
    total_netral:   int
    persen_positif: float
    persen_negatif: float
 
 
class SentimentSyncResponse(BaseModel):
    kode:         str
    sentimen:     str
    skor_sentimen: float
    total:        int
    positif:      int
    negatif:      int