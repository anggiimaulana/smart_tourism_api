# app/api/v1/endpoints/chatbot.py
# PIC: Vanes
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from typing import Optional
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import BaseResponse
from app.schemas.chatbot import ChatRequest
from app.services.chatbot_service import ChatbotService

router = APIRouter()

# Basic in-memory rate limiter (Fallback jika Redis tidak ada)
RATE_LIMIT_DURATION = 60  # seconds
RATE_LIMIT_REQUESTS = 10  # max requests per duration
_rate_limits = {}

def check_rate_limit(client_ip: str, session_token: str):
    now = time.time()
    # Gunakan IP atau session_token sebagai identifier
    identifier = session_token if session_token else client_ip
    
    if identifier not in _rate_limits:
        _rate_limits[identifier] = []
        
    # Hapus request lama
    _rate_limits[identifier] = [t for t in _rate_limits[identifier] if now - t < RATE_LIMIT_DURATION]
    
    if len(_rate_limits[identifier]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan. Silakan tunggu beberapa saat lagi."
        )
        
    _rate_limits[identifier].append(now)


@router.post(
    "/ask",
    response_model=BaseResponse,
    status_code=201,
    summary="Kirim pesan ke chatbot RAG",
    description="""
    Chatbot menjawab pertanyaan seputar **wisata, kuliner, dan nongkrong**
    di wilayah Ciayumajakuning.

    **Arsitektur RAG (CPU-friendly, tanpa FAISS/ChromaDB):**
    1. Deteksi wilayah dari teks atau koordinat GPS
    2. PostgreSQL Full-Text Search → ambil top-K dokumen relevan
    3. Format dokumen jadi konteks teks
    4. Kirim konteks + pertanyaan ke Gemini 1.5 Flash
    5. Return jawaban + referensi tempat

    **Catatan session:**
    - Jika `session_token` kosong → sesi baru dibuat otomatis
    - Kirim `session_token` yang sama untuk melanjutkan percakapan
    """,
)
async def ask_chatbot(
    request: Request,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug_info: Optional[bool] = Header(False, alias="X-Debug-Info"),
):
    """
    Latitude & longitude opsional — digunakan untuk mendeteksi wilayah terdekat.
    """
    # Rate Limiting Dasar
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip, payload.session_token)
    
    service = ChatbotService()
    result = await service.ask(payload, db, user_id=user_id, debug=bool(debug_info or getattr(payload, "debug", False)))
    return BaseResponse(data=result)


@router.get(
    "/history/{session_token}",
    response_model=BaseResponse,
    summary="Ambil riwayat percakapan berdasarkan session token",
)
async def get_history(session_token: str, db: AsyncSession = Depends(get_db)):
    """
    Return semua pesan (user + assistant) dalam sesi ini.
    """
    service = ChatbotService()
    result = await service.get_history(session_token, db)
    if not result:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")
    return BaseResponse(data=result)


@router.delete(
    "/history/{session_token}",
    response_model=BaseResponse,
    summary="Hapus riwayat percakapan (reset sesi)",
)
async def clear_history(session_token: str, db: AsyncSession = Depends(get_db)):
    """
    Mengosongkan array messages di chatbot_sessions.
    Session token tetap valid — percakapan dimulai dari awal.
    """
    service = ChatbotService()
    await service.clear_session(session_token, db)
    return BaseResponse(message="Riwayat percakapan berhasil dihapus")