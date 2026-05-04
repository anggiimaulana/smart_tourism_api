# app/api/v1/endpoints/chatbot.py
# PIC: Vanes
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import BaseResponse
from app.schemas.chatbot import ChatRequest
from app.services.chatbot_service import ChatbotService

router = APIRouter()


@router.post(
    "/ask",
    response_model=BaseResponse,
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
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Latitude & longitude opsional — digunakan untuk mendeteksi wilayah terdekat.
    """
    # TODO: implementasi di ChatbotService
    # service = ChatbotService()
    # result  = await service.ask(payload, db)
    # return BaseResponse(data=result)
    raise HTTPException(status_code=501, detail="Implementasi di ChatbotService — Vanes")


@router.get(
    "/history/{session_token}",
    response_model=BaseResponse,
    summary="Ambil riwayat percakapan berdasarkan session token",
)
async def get_history(session_token: str, db: AsyncSession = Depends(get_db)):
    """
    Return semua pesan (user + assistant) dalam sesi ini.
    """
    # TODO: implementasi di ChatbotService
    # service = ChatbotService()
    # result  = await service.get_history(session_token, db)
    # if not result:
    #     raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")
    # return BaseResponse(data=result)
    raise HTTPException(status_code=501, detail="Implementasi di ChatbotService — Vanes")


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
    # TODO: implementasi di ChatbotService
    # service = ChatbotService()
    # await service.clear_session(session_token, db)
    # return BaseResponse(message="Riwayat percakapan berhasil dihapus")
    raise HTTPException(status_code=501, detail="Implementasi di ChatbotService — Vanes")