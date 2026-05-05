# app/api/v1/endpoints/sentiment.py
# PIC: Anggi (Indramayu + Cirebon) & Ikhsan (Majalengka + Kuningan)
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.base import BaseResponse
from app.schemas.sentiment import SentimentRequest, SentimentBatchRequest
from app.services.sentiment_service import SentimentService

router = APIRouter()


@router.post(
    "/predict",
    response_model=BaseResponse,
    summary="Prediksi sentimen satu ulasan",
    description="""
    Kirim satu teks ulasan, dapatkan label sentimen + confidence score.

    **Model yang tersedia:**
    - `indobert` — akurasi tertinggi, butuh model hasil training Colab
    - `naive_bayes`, `svm`, `decision_tree` — baseline, lebih ringan

    Hasil prediksi otomatis disimpan ke tabel `sentiment_results`.
    """,
)
async def predict_sentiment(
    payload: SentimentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Error 503 = model file belum tersedia di folder ml/sentiment/.
    Jalankan training di Colab terlebih dahulu.
    """
    service = SentimentService()
    result = await service.predict_and_save(payload, db)
    return BaseResponse(data=result)


@router.post(
    "/predict/batch",
    response_model=BaseResponse,
    summary="Prediksi sentimen massal (maks. 100 ulasan per request)",
)
async def predict_batch(
    payload: SentimentBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Digunakan untuk memproses hasil scraping massal dari Google Maps.
    Proses berjalan secara berurutan (sequential), bukan parallel.
    """
    service = SentimentService()
    results = await service.predict_batch(payload.items, db)
    return BaseResponse(data=results)


@router.get(
    "/summary/{wilayah}",
    response_model=BaseResponse,
    summary="Ringkasan sentimen per wilayah",
)
async def get_summary(
    wilayah: Literal["Indramayu","Cirebon","Majalengka","Kuningan"],
    tipe_tempat: Literal["wisata","kuliner","nongkrong","all"] = Query("all"),
    db: AsyncSession = Depends(get_db),
):
    """
    Mengembalikan agregat: total ulasan, jumlah positif/negatif, persentase.
    """
    service = SentimentService()
    result = await service.get_summary(wilayah, tipe_tempat, db)
    return BaseResponse(data=result)


@router.post(
    "/sync/{tipe_tempat}/{kode}",
    response_model=BaseResponse,
    summary="[Admin] Sinkronisasi label sentimen ke tabel utama",
    dependencies=[Depends(require_admin)],
    description="""
    Hitung ulang agregat dari `sentiment_results` lalu update kolom
    `sentimen` dan `skor_sentimen` di tabel wisata/kuliner/nongkrong.

    Panggil endpoint ini setelah batch predict selesai.
    """,
)
async def sync_sentimen(
    tipe_tempat: Literal["wisata","kuliner","nongkrong"],
    kode: str,
    db: AsyncSession = Depends(get_db),
):
    # TODO: implementasi di SentimentService
    # service = SentimentService()
    # result  = await service.sync_sentimen(tipe_tempat, kode, db)
    # return BaseResponse(message="Sentimen berhasil disinkronisasi", data=result)
    raise HTTPException(status_code=501, detail="Implementasi di SentimentService — Admin")
