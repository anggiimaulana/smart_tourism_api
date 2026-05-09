"""Chatbot service template.

Target kerja berdasarkan README:
1. Deteksi wilayah dari pesan atau koordinat pengguna.
2. Ambil konteks relevan dari PostgreSQL Full-Text Search.
3. Susun prompt dan kirim ke Gemini.
4. Simpan percakapan ke chatbot_sessions.
5. Sediakan history dan reset session token.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import math
import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chatbot import ChatHistoryResponse, ChatRequest, ChatResponse

# Import dari prompts/chatbot_prompts.py
from prompts.chatbot_prompts import (
    SYSTEM_PROMPT,
    MAIN_PROMPT_TEMPLATE,
    FALLBACK_PROMPT,
    format_doc,
    format_lokasi,
)

# Inisialisasi Gemini API (Library: google-generativeai)
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY tidak ditemukan di environment variables!")

# Konfigurasi Library
genai.configure(api_key=GEMINI_API_KEY)

# Gunakan model yang tersedia dan stabil
GEMINI_MODEL = genai.GenerativeModel("gemini-2.0-flash-lite")


class ChatbotService:
    """Async service for chatbot workflows using RAG Pipeline."""

    @staticmethod
    def _timestamp() -> str:
        return datetime.utcnow().isoformat()

    # ========================================================================
    # SUBTASK 3 — Geolokasi & Session Functions
    # ========================================================================

    @staticmethod
    def detect_wilayah_from_text(text: str) -> str | None:
        """
        Subtask 3: Cek keyword Cirebon/Indramayu/Majalengka/Kuningan dalam teks user.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Mapping keyword ke nama wilayah resmi
        wilayah_keywords = {
            "cirebon": "Cirebon",
            "indramayu": "Indramayu", 
            "majalengka": "Majalengka",
            "kuningan": "Kuningan",
            # Tambah variasi penulisan
            "cirebonan": "Cirebon",
            "indramayuan": "Indramayu",
        }
        
        for keyword, wilayah in wilayah_keywords.items():
            if keyword in text_lower:
                return wilayah
        
        return None

    @staticmethod
    def nearest_wilayah(latitude: float, longitude: float) -> str | None:
        """
        Subtask 3: Hitung haversine ke 4 pusat wilayah → return terdekat.
        
        Koordinat pusat kota (approximate):
        - Cirebon: -6.7063, 108.5571
        - Indramayu: -6.3333, 108.3167
        - Majalengka: -6.8361, 108.2278
        - Kuningan: -6.9778, 108.4833
        """
        if latitude is None or longitude is None:
            return None
        
        # Koordinat pusat kota (dalam desimal)
        WILAYAH_CENTERS = {
            "Cirebon": (-6.7063, 108.5571),
            "Indramayu": (-6.3333, 108.3167),
            "Majalengka": (-6.8361, 108.2278),
            "Kuningan": (-6.9778, 108.4833),
        }
        
        def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            """
            Hitung jarak antara dua titik koordinat menggunakan Haversine formula.
            Return jarak dalam kilometer.
            """
            R = 6371.0  # Radius bumi dalam kilometer
            
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)
            
            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad
            
            a = (math.sin(dlat / 2) ** 2 + 
                 math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            
            return R * c
        
        # Hitung jarak ke semua wilayah
        distances = {}
        for wilayah, (center_lat, center_lon) in WILAYAH_CENTERS.items():
            distance = haversine(latitude, longitude, center_lat, center_lon)
            distances[wilayah] = distance
        
        # Return wilayah dengan jarak terdekat
        nearest = min(distances, key=distances.get)
        return nearest

    async def get_or_create_session(
        self,
        session_token: str,
        db: AsyncSession,
        latitude: float | None = None,
        longitude: float | None = None,
        wilayah: str | None = None
    ) -> dict:
        """
        Subtask 3: Buat sesi baru atau ambil yang sudah ada dari chatbot_sessions.
        
        Returns:
            dict dengan keys: session_token, messages, wilayah_terdeteksi, is_new
        """
        # Cek apakah session sudah ada
        row = await db.execute(
            text("""
                SELECT session_token, messages, wilayah_terdeteksi, latitude, longitude 
                FROM chatbot_sessions 
                WHERE session_token = :token
            """),
            {"token": session_token},
        )
        existing = row.fetchone()
        
        if existing:
            # Session sudah ada, return data existing
            return {
                "session_token": existing.session_token,
                "messages": list(existing.messages or []),
                "wilayah_terdeteksi": existing.wilayah_terdeteksi or wilayah,
                "latitude": existing.latitude or latitude,
                "longitude": existing.longitude or longitude,
                "is_new": False
            }
        else:
            # Session belum ada, buat baru
            new_token = session_token or str(uuid4())
            
            # Deteksi wilayah dari koordinat jika belum ada
            if not wilayah and latitude and longitude:
                wilayah = self.nearest_wilayah(latitude, longitude)
            
            await db.execute(
                text("""
                    INSERT INTO chatbot_sessions 
                    (id, session_token, messages, latitude, longitude, wilayah_terdeteksi, created_at)
                    VALUES (:id, :token, '[]'::jsonb, :lat, :lon, :wilayah, NOW())
                """),
                {
                    "id": str(uuid4()),
                    "token": new_token,
                    "lat": latitude,
                    "lon": longitude,
                    "wilayah": wilayah,
                },
            )
            await db.commit()
            
            return {
                "session_token": new_token,
                "messages": [],
                "wilayah_terdeteksi": wilayah,
                "latitude": latitude,
                "longitude": longitude,
                "is_new": True
            }

    async def save_session(
        self,
        token: str,
        messages: list,
        wilayah: str | None,
        db: AsyncSession
    ) -> None:
        """
        Subtask 3: Update array messages di DB.
        """
        await db.execute(
            text("""
                UPDATE chatbot_sessions
                SET messages = CAST(:messages AS jsonb),
                    wilayah_terdeteksi = COALESCE(:wilayah, wilayah_terdeteksi),
                    updated_at = NOW()
                WHERE session_token = :token
            """),
            {
                "messages": json.dumps(messages),
                "wilayah": wilayah,
                "token": token,
            },
        )
        await db.commit()

    # ========================================================================
    # SUBTASK 2 — RAG Pipeline Functions
    # ========================================================================

    @staticmethod
    def build_fts_query(user_message: str) -> str:
        """Subtask 2: Konversi pesan user ke tsquery PostgreSQL"""
        stopwords = {
            "yang", "dan", "di", "ke", "dari", "untuk", "dengan", 
            "pada", "adalah", "atau", "ini", "itu", "jika", "maka",
            "dimana", "bagaimana", "apa", "tolong", "mohon", "bisakah",
            "apakah", "sebutkan", "carikan", "cari", "info", "informasi"
        }
        words = user_message.lower().split()
        filtered_words = [w for w in words if w not in stopwords and len(w) > 2]
        
        if filtered_words:
            return " | ".join(filtered_words)
        return user_message.lower()

    @staticmethod
    async def retrieve_from_db(
        db: AsyncSession, 
        user_message: str, 
        wilayah_filter: str | None = None, 
        top_k: int = 3  # ✅ Optimasi: dikurangi dari 5 ke 3 untuk hemat token
    ) -> list:
        """Subtask 2: Query FTS via v_all_tempat, fallback ILIKE jika hasil kosong"""
        tsquery = ChatbotService.build_fts_query(user_message)
        
        # Primary: Full Text Search (Gunakan kolom 'fts' bukan 'tempat_fts')
        query_fts = text("""
            SELECT * FROM v_all_tempat 
            WHERE fts @@ to_tsquery('indonesian', :tsquery)
            ORDER BY ts_rank(fts, to_tsquery('indonesian', :tsquery)) DESC
            LIMIT :limit
        """)
        result_fts = await db.execute(query_fts, {"tsquery": tsquery, "limit": top_k})
        docs = result_fts.fetchall()
        
        # Fallback: ILIKE jika FTS kosong
        if not docs:
            query_like = text("""
                SELECT * FROM v_all_tempat 
                WHERE nama ILIKE :pattern OR deskripsi ILIKE :pattern
                LIMIT :limit
            """)
            result_like = await db.execute(query_like, {
                "pattern": f"%{user_message}%", 
                "limit": top_k
            })
            docs = result_like.fetchall()
        
        # Filter wilayah jika ada
        if wilayah_filter and docs:
            docs = [d for d in docs if d.wilayah and wilayah_filter.lower() in d.wilayah.lower()]
            
        return docs[:top_k]

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Helper: convert SQLAlchemy Row object to dict."""
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        return {col: getattr(row, col, None) for col in row.keys()}

    @staticmethod
    def build_context(docs: list) -> str:
        """Subtask 2: Format list dokumen menjadi string konteks terstruktur menggunakan format_doc()"""
        if not docs:
            return ""
        
        formatted_docs = [
            format_doc(ChatbotService._row_to_dict(doc), nomor=i)
            for i, doc in enumerate(docs, 1)
        ]
        return "\n\n".join(formatted_docs)

    @staticmethod
    def build_prompt(
        user_message: str, 
        context: str, 
        history: list, 
        wilayah: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None
    ) -> str:
        """Subtask 2: Gabungkan SYSTEM_PROMPT + lokasi info + konteks + riwayat + pertanyaan"""
        lokasi_info = format_lokasi(wilayah, latitude, longitude)
        
        riwayat_text = "-"
        if history:
            recent = history[-2:]  # ✅ Optimasi: dikurangi dari 3 ke 2
            riwayat_text = "\n".join([
                f"User: {h['content']}\nSITA: {h.get('content', '')}" 
                for h in recent
            ])
        
        if context:
            return MAIN_PROMPT_TEMPLATE.format(
                system_prompt=SYSTEM_PROMPT,
                lokasi_info=lokasi_info,
                konteks_db=context,
                riwayat=riwayat_text,
                pertanyaan=user_message
            )
        else:
            return FALLBACK_PROMPT.format(
                system_prompt=SYSTEM_PROMPT,
                pertanyaan=user_message
            )

    # --- Helper: Async wrapper untuk Gemini API / Mock ---
    @staticmethod
    async def _generate_gemini_response(prompt: str) -> str:
        """Wrapper async untuk memanggil Gemini API / Mock Fallback"""
        
        # ==========================================
        #  KODE GEMINI ASLI (DINONAKTIFKAN SEMENTARA)
        # ==========================================
        # from google.api_core.exceptions import ResourceExhausted
        # import time
        # 
        # def _call_gemini():
        #     for attempt in range(3):
        #         try:
        #             response = GEMINI_MODEL.generate_content(prompt)
        #             return response.text
        #         except ResourceExhausted as e:
        #             if attempt < 2:  # Retry max 2x
        #                 wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s
        #                 print(f"⚠️ Quota exhausted, retrying in {wait_time}s...")
        #                 time.sleep(wait_time)
        #                 continue
        #             else:
        #                 print("⚠️ Gemini quota exhausted. Using mock response for testing.")
        #                 return "🤖 [Demo Mode] Maaf, kuota API sedang habis. Ini contoh jawaban:\n\nBerdasarkan database, berikut rekomendasi wisata di wilayah tersebut:\n\n1. 🏖️ Pantai dengan pemandangan indah\n2. 🕌 Tempat bersejarah yang wajib dikunjungi\n3. 🍜 Kuliner khas yang enak\n\nSilakan tanya lagi untuk detail lebih lanjut! 😊"
        #         except Exception as e:
        #             print(f"❌ Gemini error: {e}")
        #             raise
        # 
        # return await asyncio.to_thread(_call_gemini)

        # ==========================================
        # ✅ KODE MOCK AKTIF (UNTUK SEKARANG)
        # ==========================================
        import re
        
        def _mock_response():
            # 1. Deteksi wilayah dari prompt yang sudah disusun sistem
            wilayah = "wilayah tersebut"
            match = re.search(r"wilayah[:\s]+([A-Za-z\s]+)", prompt, re.IGNORECASE)
            if match: wilayah = match.group(1).strip()
            
            # 2. Deteksi kategori & susun jawaban kontekstual
            if any(k in prompt.lower() for k in ["kuliner", "makan", "jajan"]):
                tipe, emoji = "kuliner", "🍜"
                items = [
                    f"Nasi Jamblang khas {wilayah}",
                    f"Empal Gentong dengan bumbu rempah kuat",
                    f"Tahu Gejrot pedas manis segar"
                ]
            elif any(k in prompt.lower() for k in ["nongkrong", "cafe", "ngopi"]):
                tipe, emoji = "tempat nongkrong", "☕"
                items = [
                    f"Cafe dengan view kota {wilayah}",
                    f"Spot kopi lokal yang tenang",
                    f"Co-working space nyaman & WiFi kencang"
                ]
            else:
                tipe, emoji = "wisata", "🏞️"
                items = [
                    f"Pantai sunset terbaik di {wilayah}",
                    f"Destinasi sejarah yang wajib dikunjungi",
                    f"Wisata alam instagramable"
                ]
                
            # 3. Format jawaban rapi ala chatbot
            return f"""{emoji} Halo! Berdasarkan database wisata, berikut rekomendasi {tipe} di **{wilayah}**:

1. {items[0]}
2. {items[1]}
3. {items[2]}

💡 *Tips*: 
- Cek link_maps untuk lokasi persisnya.
- Kunjungi saat weekday agar tidak ramai.
- Bawa uang cash untuk tempat yang belum terima QRIS.

Mau detail salah satu tempat atau cari kategori lain? """
        
        # Jalankan di thread agar tidak blocking event loop FastAPI
        return await asyncio.to_thread(_mock_response)

    # ========================================================================
    # Metode Utama (Menggunakan Subtask 2 & 3)
    # ========================================================================

    async def ask(self, payload: ChatRequest, db: AsyncSession) -> ChatResponse:
        """
        Method ask yang sudah direfactor menggunakan fungsi Subtask 2 & 3.
        """
        # 1. Deteksi wilayah dari text (Subtask 3)
        wilayah_text = self.detect_wilayah_from_text(payload.message)
        
        # 2. Deteksi wilayah dari koordinat (jika ada) (Subtask 3)
        wilayah_geo = None
        if payload.latitude and payload.longitude:
            wilayah_geo = self.nearest_wilayah(payload.latitude, payload.longitude)
        
        # Prioritaskan wilayah dari text, fallback ke geolokasi
        wilayah = wilayah_text or wilayah_geo
        
        # 3. Get or create session (Subtask 3)
        session_data = await self.get_or_create_session(
            session_token=payload.session_token,
            db=db,
            latitude=payload.latitude,
            longitude=payload.longitude,
            wilayah=wilayah
        )
        
        session_token = session_data["session_token"]
        history = session_data["messages"]
        wilayah = wilayah or session_data["wilayah_terdeteksi"]
        
        # 4. RAG Pipeline (Subtask 2)
        docs = await self.retrieve_from_db(db, payload.message, wilayah, top_k=3)
        context = self.build_context(docs)
        
        prompt = self.build_prompt(
            user_message=payload.message,
            context=context,
            history=history,
            wilayah=wilayah,
            latitude=payload.latitude,
            longitude=payload.longitude
        )
        
        answer = await self._generate_gemini_response(prompt)
        
        # 5. Simpan message ke history
        user_message_dict = {
            "role": "user",
            "content": payload.message,
            "timestamp": self._timestamp(),
        }
        assistant_message = {
            "role": "assistant",
            "content": answer,
            "timestamp": self._timestamp(),
        }
        
        messages = list(history)
        messages.extend([user_message_dict, assistant_message])
        
        # 6. Save session menggunakan fungsi baru (Subtask 3)
        await self.save_session(
            token=session_token,
            messages=messages,
            wilayah=wilayah,
            db=db
        )
        
        # 7. Siapkan referensi
        referensi = []
        if docs:
            referensi = [
                {
                    "nama": d.nama,
                    "tipe": getattr(d, 'tipe', 'wisata'),
                    "wilayah": getattr(d, 'wilayah', ''),
                    "link_maps": getattr(d, 'link_google_maps', None),
                } 
                for d in docs[:3]
            ]
        
        return ChatResponse(
            session_token=session_token,
            answer=answer,
            wilayah_terdeteksi=wilayah,
            referensi=referensi,
            messages_count=len(messages),
        )

    @staticmethod
    def _detect_wilayah(message: str, latitude: float | None, longitude: float | None) -> str | None:
        """Deteksi wilayah dari pesan atau koordinat. (Legacy - tetap dipertahankan untuk backward compatibility)"""
        lower = message.lower()
        wilayah_map = {
            "indramayu": "Indramayu",
            "cirebon": "Cirebon",
            "majalengka": "Majalengka",
            "kuningan": "Kuningan"
        }
        for keyword, wilayah in wilayah_map.items():
            if keyword in lower:
                return wilayah
                
        if latitude is not None and longitude is not None:
            return "Indramayu"
        return None

    async def get_history(self, session_token: str, db: AsyncSession) -> ChatHistoryResponse:
        """Ambil riwayat percakapan berdasarkan session token."""
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
        """Hapus riwayat percakapan untuk session tertentu."""
        await db.execute(
            text("UPDATE chatbot_sessions SET messages = '[]'::jsonb WHERE session_token = :token"),
            {"token": session_token},
        )
        await db.commit()


__all__ = ["ChatbotService"]