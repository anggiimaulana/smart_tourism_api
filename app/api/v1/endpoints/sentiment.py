# app/api/v1/endpoints/sentiment.py
# PIC: Anggi (Indramayu + Cirebon) & Ikhsan (Majalengka + Kuningan)
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.base import BaseResponse
from app.services.sentiment_service import SentimentService

router = APIRouter()


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


@router.get(
    "/summary-all",
    response_model=BaseResponse,
    summary="Ringkasan sentimen semua wilayah",
)
async def get_summary_all(
    db: AsyncSession = Depends(get_db),
):
    """
    Mengembalikan list agregat untuk 4 wilayah (Indramayu, Cirebon, Majalengka, Kuningan).
    Cocok untuk chart perbandingan antar wilayah.
    """
    service = SentimentService()
    results = await service.get_summary_all(db)
    return BaseResponse(data=results)


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
    service = SentimentService()
    result  = await service.sync_sentimen(tipe_tempat, kode, db)
    return BaseResponse(message="Sentimen berhasil disinkronisasi", data=result)


@router.post(
    "/sync-all",
    response_model=BaseResponse,
    summary="[Admin] Sinkronisasi SEMUA label sentimen",
    dependencies=[Depends(require_admin)],
)
async def sync_all_sentimen(
    db: AsyncSession = Depends(get_db),
):
    """
    Update massal kolom sentimen di semua tabel (wisata, kuliner, nongkrong)
    berdasarkan data yang ada di `sentiment_results`.
    """
    service = SentimentService()
    result  = await service.sync_all(db)
    return BaseResponse(message="Semua data berhasil disinkronisasi", data=result)
