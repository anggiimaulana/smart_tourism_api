"""Chatbot service template.

Target kerja berdasarkan README:
1. Deteksi wilayah dari pesan atau koordinat pengguna.
2. Ambil konteks relevan dari PostgreSQL Full-Text Search.
3. Susun prompt dan kirim ke Gemini 1.5 Flash.
4. Simpan percakapan ke chatbot_sessions.
5. Sediakan history dan reset session token.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chatbot import ChatHistoryResponse, ChatRequest, ChatResponse


class ChatbotService:
	"""Async service placeholder for RAG chatbot workflows."""

	TODO_LIST = [
		"Implement region detection from message content or GPS coordinates.",
		"Implement PostgreSQL FTS retrieval for relevant tourism context.",
		"Implement Gemini prompt assembly and answer generation.",
		"Persist messages and references in chatbot_sessions.",
		"Implement history fetch and session reset helpers.",
	]

	async def ask(self, payload: ChatRequest, db: AsyncSession) -> ChatResponse:
		raise NotImplementedError("TODO: implement chatbot retrieval-augmented generation")

	async def get_history(self, session_token: str, db: AsyncSession) -> ChatHistoryResponse:
		raise NotImplementedError("TODO: implement chatbot history retrieval")

	async def clear_session(self, session_token: str, db: AsyncSession) -> None:
		raise NotImplementedError("TODO: implement chatbot session reset")


__all__ = ["ChatbotService"]
