# app/api/v1/endpoints/recommendation.py
# PIC: Rifqy
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_optional
from app.schemas.base import BaseResponse
from app.schemas.recommendation import (
    RecommendationRequest,
    PlanningRequest,
    TrackHistoryRequest,
)
from app.services.recommendation_service import RecommendationService

router = APIRouter()


@router.post(
    "/",
    response_model=BaseResponse,
    summary="Dapatkan rekomendasi wisata personal",
    description="""
    Mengembalikan hingga 10 rekomendasi tempat berdasarkan strategi berlapis:

    1. **personal** — collaborative filtering dari riwayat user (butuh login + riwayat)
    2. **nearby** — berdasarkan jarak dari koordinat user (butuh lat/lon)
    3. **popular** — fallback: rating tinggi + sentimen positif (tanpa login OK)

    Sentimen positif selalu diprioritaskan dalam semua mode.
    """,
)
async def get_recommendations(
    payload: RecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """
    Endpoint ini bisa diakses tanpa login.
    Jika login, user_id diambil otomatis dari token.
    """
    if current_user:
        payload.user_id = str(current_user.id)
    service = RecommendationService()
    result = await service.recommend(payload, db)
    return BaseResponse(data=result)


@router.post(
    "/planning",
    response_model=BaseResponse,
    summary="Buat itinerary wisata otomatis",
    description="""
    Menghasilkan rencana wisata per hari berdasarkan:
    - Wilayah yang dipilih (bisa multi-wilayah)
    - Jumlah hari (1–14)
    - Budget total
    - Preferensi kategori (Alam, Kuliner Khas, Santai, dll.)
    - Tanggal mulai (opsional)

    Output: jadwal per hari dengan rekomendasi tempat yang sudah diurutkan.
    """,
)
async def create_planning(
    payload: PlanningRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    if current_user:
        payload.user_id = str(current_user.id)
    service = RecommendationService()
    result = await service.create_planning(payload, db)
    return BaseResponse(data=result)


@router.post(
    "/history",
    response_model=BaseResponse,
    summary="Catat interaksi user untuk model rekomendasi",
    description="""
    Dipanggil frontend setiap user melakukan:
    - `klik` — membuka detail tempat
    - `kunjungi` — menandai sudah dikunjungi
    - `simpan` — bookmark tempat
    - `rating` — memberi nilai (1.0–5.0)
    - `share` — berbagi ke sosmed

    Data ini menjadi input model collaborative filtering Rifqy.
    """,
)
async def track_history(
    payload: TrackHistoryRequest,
    db: AsyncSession = Depends(get_db),
):
    service = RecommendationService()
    try:
        await service.track_history(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BaseResponse(message="Interaksi berhasil dicatat")
