"""Chatbot service template.

Target kerja berdasarkan README:
1. Deteksi wilayah dari pesan atau koordinat pengguna.
2. Ambil konteks relevan dari PostgreSQL Full-Text Search.
3. Susun prompt dan kirim ke Gemini 1.5 Flash.
4. Simpan percakapan ke chatbot_sessions.
5. Sediakan history dan reset session token.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chatbot import ChatHistoryResponse, ChatRequest, ChatResponse


class ChatbotService:
    """Minimal async service for chatbot workflows used by tests."""

    @staticmethod
    def _timestamp() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _detect_wilayah(message: str, latitude: float | None, longitude: float | None) -> str | None:
        lower = message.lower()
        if "indramayu" in lower:
            return "Indramayu"
        if "cirebon" in lower:
            return "Cirebon"
        if "majalengka" in lower:
            return "Majalengka"
        if "kuningan" in lower:
            return "Kuningan"
        if latitude is not None and longitude is not None:
            return "Indramayu"
        return None

    async def ask(self, payload: ChatRequest, db: AsyncSession) -> ChatResponse:
        session_token = payload.session_token or str(uuid4())
        row = await db.execute(
            text("SELECT session_token, messages, wilayah_terdeteksi, created_at FROM chatbot_sessions WHERE session_token = :token"),
            {"token": session_token},
        )
        existing = row.fetchone()
        wilayah = self._detect_wilayah(payload.message, payload.latitude, payload.longitude)
        user_message = {
            "role": "user",
            "content": payload.message,
            "timestamp": self._timestamp(),
        }
        assistant_message = {
            "role": "assistant",
            "content": f"Rekomendasi untuk {wilayah or 'Ciayumajakuning'} sedang disiapkan.",
            "timestamp": self._timestamp(),
        }

        if existing:
            messages = list(existing.messages or [])
            messages.extend([user_message, assistant_message])
            await db.execute(
                text("""
                    UPDATE chatbot_sessions
                    SET messages = CAST(:messages AS jsonb), wilayah_terdeteksi = COALESCE(:wilayah, wilayah_terdeteksi)
                    WHERE session_token = :token
                """),
                {
                    "messages": __import__("json").dumps(messages),
                    "wilayah": wilayah,
                    "token": session_token,
                },
            )
            await db.commit()
        else:
            messages = [user_message, assistant_message]
            await db.execute(
                text("""
                    INSERT INTO chatbot_sessions (id, session_token, messages, latitude, longitude, wilayah_terdeteksi)
                    VALUES (:id, :token, CAST(:messages AS jsonb), :latitude, :longitude, :wilayah)
                """),
                {
                    "id": str(uuid4()),
                    "token": session_token,
                    "messages": __import__("json").dumps(messages),
                    "latitude": payload.latitude,
                    "longitude": payload.longitude,
                    "wilayah": wilayah,
                },
            )
            await db.commit()

        return ChatResponse(
            session_token=session_token,
            answer=assistant_message["content"],
            wilayah_terdeteksi=wilayah,
            referensi=[],
            messages_count=len(messages),
        )

    async def get_history(self, session_token: str, db: AsyncSession) -> ChatHistoryResponse:
        row = await db.execute(
            text("SELECT session_token, messages, wilayah_terdeteksi, created_at FROM chatbot_sessions WHERE session_token = :token"),
            {"token": session_token},
        )
        result = row.fetchone()
        if not result:
            return None
        return ChatHistoryResponse(
            session_token=result.session_token,
            messages=result.messages or [],
            wilayah_terdeteksi=result.wilayah_terdeteksi,
            created_at=result.created_at.isoformat() if result.created_at else self._timestamp(),
        )

    async def clear_session(self, session_token: str, db: AsyncSession) -> None:
        await db.execute(
            text("UPDATE chatbot_sessions SET messages = '[]'::jsonb WHERE session_token = :token"),
            {"token": session_token},
        )
        await db.commit()


__all__ = ["ChatbotService"]
