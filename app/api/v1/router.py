# app/api/v1/router.py
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    wisata,
    kuliner,
    nongkrong,
    sentiment,
    chatbot,
    recommendation,
)

router = APIRouter()

# ── Auth ──────────────────────────────────────────────────────
router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"],
)

# ── Data CRUD (publik read, admin write) ──────────────────────
router.include_router(
    wisata.router,
    prefix="/wisata",
    tags=["Wisata"],
)
router.include_router(
    kuliner.router,
    prefix="/kuliner",
    tags=["Kuliner"],
)
router.include_router(
    nongkrong.router,
    prefix="/nongkrong",
    tags=["Nongkrong"],
)

# ── AI Systems ────────────────────────────────────────────────
router.include_router(
    sentiment.router,
    prefix="/sentiment",
    tags=["AI — Analisis Sentimen"],
)
router.include_router(
    chatbot.router,
    prefix="/chatbot",
    tags=["AI — Chatbot RAG"],
)
router.include_router(
    recommendation.router,
    prefix="/recommendation",
    tags=["AI — Rekomendasi & Planning"],
)