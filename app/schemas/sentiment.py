from typing import List
from pydantic import BaseModel


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