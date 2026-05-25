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
import re
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

# ── LLM Provider Configuration ─────────────────────────────────────────────────
# Support: Gemini (default) atau Groq (fallback/alternatif)
# Set LLM_PROVIDER=groq di .env untuk pakai Groq

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" atau "groq"

# --- Groq Setup ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "compound-beta")  # atau "llama-3.3-70b-versatile"
GROQ_CLIENT = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        print("Warning: groq package not installed. Run: pip install groq")

# --- Gemini Setup ---
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    GEMINI_MODEL = genai.GenerativeModel("gemini-2.0-flash")

# Validasi: minimal satu provider harus tersedia
if not GEMINI_API_KEY and not GROQ_API_KEY:
    raise ValueError("Minimal satu API key harus diset: GEMINI_API_KEY atau GROQ_API_KEY")


class ChatbotService:
    """Async service for chatbot workflows using RAG Pipeline."""

    WILAYAH_LIST = ("Indramayu", "Cirebon", "Majalengka", "Kuningan")

    @staticmethod
    def _timestamp() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _parse_nominal_to_int(raw: str) -> int | None:
        """Parse nominal Indonesia seperti 10.000, 20rb, 1jt menjadi integer."""
        if not raw:
            return None

        value = raw.lower().replace("rp", "").replace(" ", "")
        multiplier = 1
        if value.endswith("rb") or value.endswith("k"):
            multiplier = 1_000
            value = value[:-2] if value.endswith("rb") else value[:-1]
        elif value.endswith("jt"):
            multiplier = 1_000_000
            value = value[:-2]

        value = value.replace(".", "").replace(",", "")
        if not value.isdigit():
            return None
        return int(value) * multiplier

    @classmethod
    def parse_budget_range_from_text(cls, text: str) -> tuple[int | None, int | None]:
        """Ekstrak budget min/max dari teks user jika ada."""
        if not text:
            return None, None

        lowered = text.lower()
        pair_match = re.search(r"((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)\s*(?:-|sampai|hingga|to)\s*((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)", lowered)
        if pair_match:
            bmin = cls._parse_nominal_to_int(pair_match.group(1))
            bmax = cls._parse_nominal_to_int(pair_match.group(2))
            if bmin is not None and bmax is not None:
                return (min(bmin, bmax), max(bmin, bmax))

        single_match = re.search(r"budget\s*(?:di|sekitar|maks)?\s*((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)", lowered)
        if single_match:
            nominal = cls._parse_nominal_to_int(single_match.group(1))
            if nominal is not None:
                return 0, nominal

        return None, None

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
        wilayah: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        Subtask 3: Buat sesi baru atau ambil yang sudah ada dari chatbot_sessions.
        
        Returns:
            dict dengan keys: session_token, messages, wilayah_terdeteksi, is_new
        """
        # Cek apakah session sudah ada
        row = await db.execute(
            text("""
                SELECT session_token, messages, wilayah_terdeteksi, latitude, longitude, user_id
                FROM chatbot_sessions 
                WHERE session_token = :token
            """),
            {"token": session_token},
        )
        existing = row.fetchone()
        
        if existing:
            # Session sudah ada, return data existing
            # Jika session sudah ada tapi belum terkait ke user dan sekarang ada user_id,
            # kaitkan session tersebut ke user agar history tersimpan ke akun.
            if user_id and (not existing.user_id):
                await db.execute(
                    text("""
                        UPDATE chatbot_sessions SET user_id = :user_id WHERE session_token = :token
                    """),
                    {"user_id": user_id, "token": existing.session_token},
                )
                await db.commit()

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
                    (id, user_id, session_token, messages, latitude, longitude, wilayah_terdeteksi, created_at)
                    VALUES (:id, :user_id, :token, '[]'::jsonb, :lat, :lon, :wilayah, NOW())
                """),
                {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "token": new_token,
                    "lat": latitude,
                    "lon": longitude,
                    "wilayah": wilayah if wilayah in ("Indramayu", "Cirebon", "Majalengka", "Kuningan") else None,
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
        top_k: int = 3,
        lat: float = None,
        lng: float = None,
        budget_min: int | None = None,
        budget_max: int | None = None,
    ) -> list:
        """
        Retrieval dari database PostgreSQL menggunakan FTS dan Filter Wilayah.
        Jika lat & lng tersedia, akan diurutkan berdasarkan jarak terdekat.
        """
        import re
        
        msg_lower = user_message.lower()
        
        # Deteksi tipe tempat dari pesan user
        tipe_filter = None
        if any(k in msg_lower for k in ["nongkrong", "cafe", "kafe", "coffee", "kopi", "ngopi", "hangout"]):
            tipe_filter = "nongkrong"
        elif any(k in msg_lower for k in ["kuliner", "makan", "makanan", "restoran", "warung", "masakan", "menu"]):
            tipe_filter = "kuliner"
        elif any(k in msg_lower for k in ["wisata", "pantai", "gunung", "air terjun", "taman", "museum", "candi"]):
            tipe_filter = "wisata"

        # Clean query — hapus stopwords agar FTS lebih efektif
        stopwords = {
            "yang", "dan", "di", "ke", "dari", "untuk", "dengan",
            "pada", "adalah", "atau", "ini", "itu", "jika", "maka",
            "dimana", "bagaimana", "apa", "tolong", "mohon", "bisakah",
            "apakah", "sebutkan", "carikan", "cari", "info", "informasi",
            "rekomendasikan", "rekomendasi", "rekomen", "bagus", "enak",
            "terbaik", "terdekat", "murah", "seru", "keren", "populer",
            "ada", "bisa", "mau", "ingin", "saya", "aku", "gue", "gw",
            "berikan", "kasih", "tempat", "kekinian", "hits",
        }
        words = re.sub(r'[^\w\s]', '', user_message).lower().split()
        filtered_words = [w for w in words if w not in stopwords and len(w) > 2]
        
        # Buat query string dengan OR operator untuk FTS
        if filtered_words:
            query_str = " | ".join(filtered_words)
        else:
            query_str = "wisata | kuliner | nongkrong"

        # Tentukan kolom order (default ranking FTS)
        order_clause = "rank DESC"
        distance_col = ""
        
        # Jika ada koordinat, gunakan formula Haversine untuk hitung jarak (dalam KM)
        if lat is not None and lng is not None:
            distance_col = f""", 
                (6371 * acos(
                    cos(radians({lat})) * cos(radians(latitude)) * 
                    cos(radians(longitude) - radians({lng})) + 
                    sin(radians({lat})) * sin(radians(latitude))
                )) AS distance"""
            order_clause = "distance ASC"

        # Build WHERE clause
        where_parts = ["fts @@ to_tsquery('indonesian', :query)"]
        params = {"query": query_str, "limit": top_k}
        
        if wilayah_filter:
            where_parts.append("wilayah ILIKE :wilayah")
            params["wilayah"] = wilayah_filter
        if tipe_filter:
            where_parts.append("tipe = :tipe")
            params["tipe"] = tipe_filter
        if budget_min is not None:
            where_parts.append("COALESCE(harga_max, harga_min, 0) >= :budget_min")
            params["budget_min"] = budget_min
        if budget_max is not None:
            where_parts.append("COALESCE(harga_min, 0) <= :budget_max")
            params["budget_max"] = budget_max
        
        where_clause = " AND ".join(where_parts)

        # 1. Full Text Search (FTS) — pakai to_tsquery dengan OR
        sql_fts = text(f"""
            SELECT *, ts_rank(fts, to_tsquery('indonesian', :query)) as rank
            {distance_col}
            FROM v_all_tempat
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT :limit
        """)
        
        result = await db.execute(sql_fts, params)
        docs = result.fetchall()
        
        # 2. Fallback: FTS tanpa tipe filter jika kosong
        if not docs and tipe_filter:
            where_parts_no_tipe = [p for p in where_parts if "tipe" not in p]
            where_clause_no_tipe = " AND ".join(where_parts_no_tipe)
            params_no_tipe = {k: v for k, v in params.items() if k != "tipe"}
            
            sql_fallback = text(f"""
                SELECT *, ts_rank(fts, to_tsquery('indonesian', :query)) as rank
                {distance_col}
                FROM v_all_tempat
                WHERE {where_clause_no_tipe}
                ORDER BY {order_clause}
                LIMIT :limit
            """)
            result = await db.execute(sql_fallback, params_no_tipe)
            docs = result.fetchall()

        # 3. Fallback: Jika FTS kosong dan ada koordinat, ambil data terdekat
        if not docs and lat is not None and lng is not None:
            tipe_clause = f"AND tipe = '{tipe_filter}'" if tipe_filter else ""
            budget_clause = ""
            if budget_min is not None:
                budget_clause += " AND COALESCE(harga_max, harga_min, 0) >= :budget_min"
            if budget_max is not None:
                budget_clause += " AND COALESCE(harga_min, 0) <= :budget_max"
            sql_nearby = text(f"""
                SELECT *{distance_col}
                FROM v_all_tempat
                WHERE wilayah ILIKE :wilayah {tipe_clause} {budget_clause}
                ORDER BY distance ASC
                LIMIT :limit
            """)
            params_nearby = {"wilayah": wilayah_filter, "limit": top_k} if wilayah_filter else {"limit": top_k}
            if budget_min is not None:
                params_nearby["budget_min"] = budget_min
            if budget_max is not None:
                params_nearby["budget_max"] = budget_max
            result = await db.execute(sql_nearby, params_nearby)
            docs = result.fetchall()

        # 4. Fallback terakhir: ambil data populer di wilayah + tipe
        if not docs:
            tipe_clause = f"AND tipe = :tipe" if tipe_filter else ""
            budget_clause = ""
            if budget_min is not None:
                budget_clause += " AND COALESCE(harga_max, harga_min, 0) >= :budget_min"
            if budget_max is not None:
                budget_clause += " AND COALESCE(harga_min, 0) <= :budget_max"
            wilayah_clause = "WHERE wilayah ILIKE :wilayah" if wilayah_filter else "WHERE 1=1"
            params_pop = {"limit": top_k}
            if wilayah_filter:
                params_pop["wilayah"] = wilayah_filter
            if tipe_filter:
                params_pop["tipe"] = tipe_filter
            if budget_min is not None:
                params_pop["budget_min"] = budget_min
            if budget_max is not None:
                params_pop["budget_max"] = budget_max
            
            sql_popular = text(f"""
                SELECT *
                FROM v_all_tempat
                {wilayah_clause} {tipe_clause} {budget_clause}
                ORDER BY rating_google DESC NULLS LAST
                LIMIT :limit
            """)
            result = await db.execute(sql_popular, params_pop)
            docs = result.fetchall()

        # 5. Distribusi merata antar wilayah jika query multi-wilayah (tanpa filter)
        if not wilayah_filter and docs and len(docs) > 1:
            docs = ChatbotService._balance_by_wilayah(docs, top_k)

        return docs[:top_k]

    @staticmethod
    def _balance_by_wilayah(docs: list, top_k: int) -> list:
        """Distribusi hasil merata antar wilayah agar tidak condong ke 1 daerah."""
        from collections import defaultdict
        
        # Group by wilayah
        by_wilayah = defaultdict(list)
        for doc in docs:
            w = getattr(doc, 'wilayah', None) or 'Unknown'
            by_wilayah[w].append(doc)
        
        # Round-robin: ambil 1 dari tiap wilayah secara bergantian
        balanced = []
        wilayah_keys = list(by_wilayah.keys())
        idx = 0
        while len(balanced) < top_k and any(by_wilayah.values()):
            key = wilayah_keys[idx % len(wilayah_keys)]
            if by_wilayah[key]:
                balanced.append(by_wilayah[key].pop(0))
            idx += 1
            # Safety: jika sudah loop semua dan semua kosong, break
            if idx > top_k * len(wilayah_keys):
                break
        
        return balanced

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

    @classmethod
    def _build_relevant_followup_suggestions(cls, wilayah: str | None) -> str:
        """Buat contoh pertanyaan lanjutan yang relevan dengan wilayah aktif."""
        target = wilayah if wilayah in cls.WILAYAH_LIST else "Ciayumajakuning"
        if target in cls.WILAYAH_LIST:
            return (
                "\n\n**Coba tanya SITA hal lain seperti:**\n"
                f"- \"Rekomendasi wisata alam di {target}\"\n"
                f"- \"Kuliner khas {target} yang enak\"\n"
                f"- \"Tempat nongkrong yang nyaman di {target}\""
            )
        return (
            "\n\n**Coba tanya SITA hal lain seperti:**\n"
            "- \"Rekomendasi wisata alam di Indramayu\"\n"
            "- \"Kuliner legendaris Cirebon\"\n"
            "- \"Tempat nongkrong nyaman di Kuningan\""
        )

    @classmethod
    def _build_grounded_answer(
        cls,
        docs: list,
        wilayah: str | None,
        budget_min: int | None = None,
        budget_max: int | None = None,
    ) -> str:
        """Jawaban deterministic berbasis dokumen DB agar bebas halusinasi."""
        if not docs:
            budget_text = ""
            if budget_min is not None or budget_max is not None:
                low = f"Rp{budget_min:,}" if budget_min is not None else "bebas"
                high = f"Rp{budget_max:,}" if budget_max is not None else "bebas"
                budget_text = f" untuk rentang budget {low} - {high}"
            return (
                f"Maaf, SITA belum menemukan data yang cocok{budget_text}. "
                "Silakan coba ubah kata kunci, wilayah, atau rentang budget."
            )

        scope = wilayah if wilayah in cls.WILAYAH_LIST else "Ciayumajakuning"
        lines = [f"🏞️ Berikut rekomendasi wisata di **{scope}** dari data yang tersedia:"]

        for i, doc in enumerate(docs[:3], 1):
            d = cls._row_to_dict(doc)
            nama = d.get("nama", "-")
            maps = d.get("link_google_maps") or "Tidak tersedia"
            area = d.get("wilayah") or "-"
            harga_min = d.get("harga_min")
            harga_max = d.get("harga_max")
            if isinstance(harga_min, int) and isinstance(harga_max, int):
                if harga_min == 0 and harga_max == 0:
                    harga_text = "Gratis"
                elif harga_min == harga_max:
                    harga_text = f"Rp{harga_min:,}"
                else:
                    harga_text = f"Rp{harga_min:,} - Rp{harga_max:,}"
            else:
                harga_text = "Tidak tersedia"
            lines.append(f"{i}. **{nama}** ({area}) - Estimasi biaya: {harga_text} - Maps: {maps}")

        lines.append("\nSemua rekomendasi di atas diambil dari data database Smart Tourism.")
        lines.append(cls._build_relevant_followup_suggestions(wilayah))
        lines.append("\nAda lagi yang bisa SITA bantu?")
        return "\n".join(lines)

    @classmethod
    def _is_answer_grounded(cls, answer: str, docs: list, wilayah_filter: str | None) -> bool:
        """Validasi ringan agar jawaban tidak keluar konteks dokumen/wilayah."""
        if not answer:
            return False

        lowered = answer.lower()
        if docs:
            allowed_names = {
                (cls._row_to_dict(doc).get("nama") or "").lower().strip()
                for doc in docs[:5]
            }
            allowed_names = {n for n in allowed_names if n}
            if allowed_names and not any(n in lowered for n in allowed_names):
                return False

        if wilayah_filter and wilayah_filter in cls.WILAYAH_LIST:
            for wilayah in cls.WILAYAH_LIST:
                if wilayah == wilayah_filter:
                    continue
                if wilayah.lower() in lowered:
                    return False

        return True

    # --- Helper: Async wrapper untuk LLM API (Gemini / Groq) ---
    async def _generate_gemini_response(self, prompt: str, docs: list = None) -> str:
        """Wrapper async untuk memanggil LLM API (Gemini atau Groq) dengan fallback."""
        
        import time

        # Tentukan urutan provider berdasarkan konfigurasi
        if LLM_PROVIDER == "groq" and GROQ_CLIENT:
            providers = [("groq", self._call_groq), ("gemini", self._call_gemini)]
        else:
            providers = [("gemini", self._call_gemini), ("groq", self._call_groq)]

        for provider_name, call_fn in providers:
            try:
                result = await asyncio.to_thread(call_fn, prompt)
                if result:
                    return result
            except Exception as e:
                print(f"Warning: {provider_name} failed: {e}")
                continue

        # Semua provider gagal → fallback ke mock
        print("Warning: All LLM providers failed. Using mock response.")
        return ChatbotService._get_mock_fallback(prompt, docs)

    @staticmethod
    def _call_gemini(prompt: str) -> str | None:
        """Call Gemini API dengan retry."""
        if not GEMINI_MODEL:
            return None
        
        from google.api_core.exceptions import ResourceExhausted
        import time

        for attempt in range(2):
            try:
                response = GEMINI_MODEL.generate_content(prompt)
                return response.text
            except ResourceExhausted:
                if attempt < 1:
                    wait_time = 2 ** attempt
                    print(f"Warning: Gemini quota exhausted, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print("Warning: Gemini quota exhausted.")
                    return None
            except Exception as e:
                print(f"Error: Gemini error: {e}")
                return None
        return None

    @staticmethod
    def _call_groq(prompt: str) -> str | None:
        """Call Groq API (OpenAI-compatible)."""
        if not GROQ_CLIENT:
            return None
        
        try:
            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "Kamu adalah SITA, asisten pariwisata Ciayumajakuning. Jawab dalam Bahasa Indonesia dengan ramah dan informatif. Hanya jawab pertanyaan seputar wisata, kuliner, dan tempat nongkrong di wilayah Cirebon, Indramayu, Majalengka, dan Kuningan."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error: Groq error: {e}")
            return None

    @staticmethod
    def _get_mock_fallback(prompt: str, docs: list = None) -> str:
        """Logic mock yang cerdas, aman, dan informatif (Fallback RAG)."""
        import re
        import html
        
        # 1. Sanitasi & Pembersihan Input
        def sanitize(text: str) -> str:
            import string
            # Hapus tanda baca agar "bajo?" jadi "bajo"
            text = text.translate(str.maketrans('', '', string.punctuation))
            return text.lower().strip()[:500]

        # Ambil bagian PERTANYAAN USER saja dari prompt agar tidak rancu dengan SYSTEM_PROMPT
        user_part_raw = prompt.split("PERTANYAAN USER:")[-1].split("JAWABAN SITA:")[0] if "PERTANYAAN USER:" in prompt else prompt
        user_part = sanitize(user_part_raw)

        # 1. Deteksi wilayah
        wilayah = "wilayah tersebut"
        match = re.search(r"wilayah[:\s]+([A-Za-z\s]+)", prompt, re.IGNORECASE)
        if match: wilayah = match.group(1).strip()
        
        # 2. Ambil data dari docs jika ada
        items = []

        # --- 1. DETEKSI OUT-OF-SCOPE & IRRELEVANT (PRIORITAS UTAMA) ---
        out_of_scope_keywords = [
            "jakarta", "bandung", "jogja", "yogyakarta", "bali", "lombok", "surabaya", 
            "semarang", "malang", "labuan", "labuhan", "bajo", "raja ampat", "medan", 
            "makassar", "singapura", "malaysia", "monas", "borobudur", "prambanan"
        ]
        
        irrelevant_topics = [
            "politik", "presiden", "agama", "tugas sekolah", "matematika", "rumus", 
            "coding", "programming", "uang", "pinjol", "jodoh", "pacar", "nikah",
            "berita", "gempa", "kriminal", "hantu", "misteri", "siapa penemu", "siapa yang membuat"
        ]

        is_out_of_scope = any(k in user_part for k in out_of_scope_keywords)
        is_irrelevant = any(k in user_part for k in irrelevant_topics)

        if is_out_of_scope:
            return f"🔍 **Maaf ya, jangkauan informasi SITA saat ini terbatas di wilayah Ciayumajakuning saja.**\n\nSITA belum bisa memberikan informasi untuk tempat di luar Cirebon, Indramayu, Majalengka, dan Kuningan. Silakan tanya SITA tentang destinasi di wilayah tersebut ya!"
        
        if is_irrelevant:
            return f"🤖 **Maaf banget! SITA hanya bisa menjawab pertanyaan seputar pariwisata, kuliner, dan tempat nongkrong.**\n\nSITA tidak dilatih untuk menjawab topik di luar Ciayumajakuning atau topik umum lainnya. Yuk, tanya SITA tentang rekomendasi liburan saja!"

        # --- 2. DETEKSI IDENTITAS & SAPAAN ---
        if any(k in user_part for k in ["siapa kamu", "nama kamu", "siapa dirimu", "apa itu sita", "kamu siapa"]):
            return "Halo! Saya **SITA** (Smart Informasi Turisme Asisten), asisten virtual pariwisata Ciayumajakuning. Saya bisa bantu kamu cari info wisata, kuliner, atau tempat nongkrong keren!"
        
        # C. Cek Intent Lokasi/Alamat/Terdekat
        is_asking_location = any(k in user_part for k in ["dimana", "lokasi", "alamat", "rute", "posisi", "daerah mana"])
        is_asking_nearby = "terdekat" in user_part
        is_asking_price = any(k in user_part for k in ["harga", "biaya", "tiket", "bayar"])

        if any(k in user_part for k in ["halo", "hai", "pagi", "siang", "sore", "malam"]):
            return f"Halo! Ada yang bisa SITA bantu di {wilayah}? Saya punya banyak info tempat wisata, kuliner, dan cafe lokal lho."

        elif docs:
            # Ambil data utama
            main_doc = ChatbotService._row_to_dict(docs[0])
            main_nama = main_doc.get('nama', '').lower()
            
            # Jika FTS sudah return hasil, data dianggap relevan
            # FTS PostgreSQL sudah melakukan filtering relevansi
            is_relevant = True
            
            if not is_relevant:
                header = f"🔍 **Maaf, SITA belum menemukan data yang pas untuk '{user_part_raw.strip()}' di Ciayumajakuning.**"
                items_text = "Mungkin tempat yang kamu cari berada di luar jangkauan SITA atau ada kesalahan pengetikan nama tempat."
            else:
                # Proses Jawaban (Sudah tervalidasi relevan atau intent 'terdekat')
                main_nama_fix = main_doc.get('nama', 'Tempat tersebut')
                main_alamat = main_doc.get('alamat_lengkap', 'wilayah Ciayumajakuning')
                main_maps = main_doc.get('link_google_maps', '#')
                main_dist = main_doc.get('distance')

                # Deteksi tipe tempat dari data
                tipe = main_doc.get('tipe', 'wisata')
                if tipe == 'kuliner':
                    emoji = "🍽️"
                elif tipe == 'nongkrong':
                    emoji = "☕"
                else:
                    emoji = "🏞️"

                if is_asking_nearby:
                    if main_dist is not None:
                        if main_dist <= 10:
                            header = f"📍 Wah, ada yang deket banget nih! **{main_nama_fix}** cuma sekitar {main_dist:.1f} km dari lokasimu."
                        elif main_dist <= 30:
                            header = f"🚗 **{main_nama_fix}** adalah yang paling terdekat dari posisimu saat ini (sekitar {main_dist:.1f} km)."
                        else:
                            header = f"🔍 Tempat terdekat yang SITA temukan adalah **{main_nama_fix}**, jaraknya sekitar {main_dist:.1f} km. Masih oke buat dikunjungi!"
                    else:
                        header = f"📍 SITA rekomendasikan **{main_nama_fix}** sebagai destinasi terdekat yang populer di {wilayah}."
                    
                    items.append(f"Cek rutenya di sini: {main_maps}")
                    if len(docs) > 1:
                        items.append(f"\nOpsi menarik lainnya:")
                        for d in docs[1:3]:
                            d_extra = ChatbotService._row_to_dict(d)
                            d_dist = d_extra.get('distance')
                            dist_str = f" ({d_dist:.1f} km)" if d_dist else ""
                            items.append(f"- {d_extra.get('nama')}{dist_str} (Maps: {d_extra.get('link_google_maps')})")

                elif is_asking_location:
                    header = f"📍 Tentu! Untuk **{main_nama_fix}**, lokasinya berada di {main_alamat}."
                    items.append(f"Klik di sini untuk rute Maps: {main_maps}")
                elif is_asking_price:
                    h_min = main_doc.get('harga_min', 0)
                    h_max = main_doc.get('harga_max', 0)
                    harga_str = f"Rp{h_min:,} - Rp{h_max:,}" if h_min != h_max else (f"Sekitar Rp{h_min:,}" if h_min > 0 else "Gratis")
                    header = f"💰 Untuk estimasi biaya di **{main_nama_fix}**, siapkan sekitar {harga_str} per orang."
                    items.append(f"Maps: {main_maps}")
                else:
                    header = f"{emoji} Halo! Berikut rekomendasi {tipe} di **{wilayah}** yang mungkin kamu suka:"
                    for d in docs[:3]:
                        d_dict = ChatbotService._row_to_dict(d)
                        items.append(f"**{d_dict.get('nama')}** (Maps: {d_dict.get('link_google_maps')})")
                
                items_text = "\n".join([f"{item}" if item.startswith("-") or item.startswith("\n") else f"{i+1}. {item}" for i, item in enumerate(items)])
        else:
            header = f"🔍 **Maaf, SITA belum menemukan data yang cocok.**"
            items_text = "Pastikan tempat yang kamu cari berada di wilayah Cirebon, Indramayu, Majalengka, atau Kuningan."

        # Tambahkan Contoh Pertanyaan Relevan di akhir (sesuai wilayah aktif)
        suggestions = ChatbotService._build_relevant_followup_suggestions(wilayah)

        return f"""{header}

{items_text}

💡 *Tips*: Sebaiknya cek jam operasional atau cuaca sebelum berangkat ke lokasi.

{suggestions}

Ada lagi yang bisa SITA bantu seputar Ciayumajakuning?"""


    # ========================================================================
    # Content Safety — Tolak pertanyaan berbahaya / di luar konteks
    # ========================================================================

    @staticmethod
    def _check_content_safety(message: str) -> str | None:
        """
        Cek apakah pesan mengandung konten berbahaya atau di luar konteks pariwisata.
        Return pesan penolakan jika terdeteksi, None jika aman.
        """
        import re
        
        msg_lower = re.sub(r'[^\w\s]', '', message).lower()

        # Konten berbahaya / ilegal — HARUS ditolak
        dangerous_keywords = [
            "serangan cyber", "cyber attack", "ddos", "hack", "hacking", "hacker",
            "exploit", "malware", "ransomware", "virus komputer", "trojan",
            "phishing", "sql injection", "xss", "brute force",
            "buat bom", "membuat bom", "racun", "senjata", "narkoba", "drugs",
            "bunuh", "membunuh", "pembunuhan", "terorisme", "teroris",
            "pencurian data", "carding", "skimming", "penipuan online",
            "deepfake", "pornografi", "porno", "judi online", "slot online",
        ]

        # Topik di luar konteks pariwisata — tolak dengan halus
        irrelevant_topics = [
            "politik", "presiden", "pemilu", "partai", "pilkada",
            "agama", "aliran sesat", "kafir", "halal haram",
            "tugas sekolah", "tugas kuliah", "kerjakan pr", "jawab soal",
            "matematika", "fisika", "kimia", "biologi", "rumus",
            "coding", "programming", "python", "javascript", "java", "kode program",
            "pinjol", "pinjaman online", "investasi bodong",
            "jodoh", "pacar", "mantan", "selingkuh",
            "berita terkini", "gosip artis", "selebriti",
            "resep masak",  # bukan rekomendasi tempat makan
            "cara menulis", "cara membuat essay", "cara presentasi",
            "translate", "terjemahkan",
        ]

        # Lokasi di luar Ciayumajakuning
        out_of_scope_locations = [
            "jakarta", "bandung", "jogja", "yogyakarta", "bali", "lombok",
            "surabaya", "semarang", "malang", "labuan bajo", "raja ampat",
            "medan", "makassar", "manado", "singapura", "malaysia", "thailand",
            "monas", "borobudur", "prambanan", "tanah lot", "kuta",
            "solo", "semarang", "palembang", "pontianak", "balikpapan",
        ]

        # Check dangerous content
        for keyword in dangerous_keywords:
            if keyword in msg_lower:
                return (
                    "🚫 **Maaf, SITA tidak bisa membantu permintaan tersebut.**\n\n"
                    "SITA adalah asisten pariwisata yang hanya melayani informasi seputar "
                    "wisata, kuliner, dan tempat nongkrong di Ciayumajakuning. "
                    "Permintaan yang mengandung konten berbahaya atau ilegal tidak dapat diproses.\n\n"
                    "💡 Yuk, tanya SITA hal-hal seru seperti:\n"
                    "- \"Rekomendasi pantai di Indramayu\"\n"
                    "- \"Cafe kekinian di Cirebon\"\n"
                    "- \"Wisata alam terbaik di Kuningan\"\n\n"
                    "Ada yang bisa SITA bantu seputar Ciayumajakuning?"
                )

        # Check irrelevant topics
        for keyword in irrelevant_topics:
            if keyword in msg_lower:
                return (
                    "🤖 **Maaf ya, SITA hanya bisa menjawab pertanyaan seputar pariwisata, "
                    "kuliner, dan tempat nongkrong di Ciayumajakuning.**\n\n"
                    "Pertanyaan di luar topik tersebut belum bisa SITA jawab. "
                    "Tapi kalau kamu butuh rekomendasi liburan, SITA siap bantu!\n\n"
                    "💡 Coba tanya:\n"
                    "- \"Tempat nongkrong kekinian di Majalengka\"\n"
                    "- \"Kuliner khas Indramayu yang wajib dicoba\"\n"
                    "- \"Wisata keluarga di Kuningan\"\n\n"
                    "Ada yang bisa SITA bantu?"
                )

        # Check out-of-scope locations (tapi hanya jika TIDAK menyebut Ciayumajakuning)
        mentions_ciayumajakuning = any(
            w in msg_lower for w in ["cirebon", "indramayu", "majalengka", "kuningan", "ciayumajakuning"]
        )
        if not mentions_ciayumajakuning:
            for keyword in out_of_scope_locations:
                if keyword in msg_lower:
                    return (
                        "🔍 **Maaf, jangkauan informasi SITA terbatas di wilayah Ciayumajakuning.**\n\n"
                        "SITA hanya bisa memberikan rekomendasi untuk daerah Cirebon, Indramayu, "
                        "Majalengka, dan Kuningan. Untuk destinasi di luar wilayah tersebut, "
                        "SITA belum punya datanya.\n\n"
                        "💡 Tapi kalau mau explore Ciayumajakuning, SITA punya banyak rekomendasi!\n"
                        "- \"Wisata alam di Kuningan\"\n"
                        "- \"Pantai terbaik di Indramayu\"\n"
                        "- \"Kuliner legendaris Cirebon\"\n\n"
                        "Mau coba tanya yang mana?"
                    )

        return None  # Aman, lanjut proses

    # ========================================================================
    # Metode Utama (Menggunakan Subtask 2 & 3)
    # ========================================================================

    async def ask(self, payload: ChatRequest, db: AsyncSession, user_id: str | None = None) -> ChatResponse:
        """
        Method ask yang sudah direfactor menggunakan fungsi Subtask 2 & 3.
        """
        # 0. Content Safety Check — tolak pertanyaan berbahaya/di luar konteks
        rejection = self._check_content_safety(payload.message)
        if rejection:
            # Tetap simpan ke session tapi jawab dengan penolakan halus
            session_data = await self.get_or_create_session(
                session_token=payload.session_token,
                db=db,
                latitude=payload.latitude,
                longitude=payload.longitude,
                wilayah=self.detect_wilayah_from_text(payload.message) or "Indramayu",
                user_id=user_id,
            )
            session_token = session_data["session_token"]
            history = session_data["messages"]
            
            messages = list(history)
            messages.extend([
                {"role": "user", "content": payload.message, "timestamp": self._timestamp()},
                {"role": "assistant", "content": rejection, "timestamp": self._timestamp()},
            ])
            await self.save_session(token=session_token, messages=messages, wilayah=session_data.get("wilayah_terdeteksi"), db=db)
            
            return ChatResponse(
                session_token=session_token,
                answer=rejection,
                wilayah_terdeteksi=session_data.get("wilayah_terdeteksi"),
                referensi=[],
                messages_count=len(messages),
            )

        # 1. Deteksi wilayah dari text (Subtask 3)
        wilayah_text = self.detect_wilayah_from_text(payload.message)
        
        # 2. Deteksi wilayah dari koordinat (jika ada) (Subtask 3)
        wilayah_geo = None
        if payload.latitude and payload.longitude:
            wilayah_geo = self.nearest_wilayah(payload.latitude, payload.longitude)
        
        # 3. Tentukan wilayah filter untuk query
        # Jika user sebut "ciayumajakuning" atau tidak sebut wilayah spesifik → None (semua wilayah)
        msg_lower = payload.message.lower()
        is_all_region = "ciayumajakuning" in msg_lower or "ciayumajakung" in msg_lower
        
        # Hitung berapa wilayah yang disebut
        mentioned_wilayah = []
        for w in ["cirebon", "indramayu", "majalengka", "kuningan"]:
            if w in msg_lower:
                mentioned_wilayah.append(w.capitalize())
        
        if is_all_region or len(mentioned_wilayah) > 1:
            # Multi-wilayah atau ciayumajakuning → jangan filter, ambil dari semua
            wilayah_filter = None
            wilayah = "Ciayumajakuning"
        elif len(mentioned_wilayah) == 1:
            wilayah_filter = mentioned_wilayah[0]
            wilayah = mentioned_wilayah[0]
        elif wilayah_text:
            wilayah_filter = wilayah_text
            wilayah = wilayah_text
        elif wilayah_geo:
            wilayah_filter = wilayah_geo
            wilayah = wilayah_geo
        else:
            # Tidak ada info wilayah sama sekali → ambil semua
            wilayah_filter = None
            wilayah = "Ciayumajakuning"
        
        # 4. Get or create session (Subtask 3)
        session_data = await self.get_or_create_session(
            session_token=payload.session_token,
            db=db,
            latitude=payload.latitude,
            longitude=payload.longitude,
            wilayah=wilayah,
            user_id=user_id,
        )
        
        session_token = session_data["session_token"]
        history = session_data["messages"]

        # 4.1 Parse budget range dari teks user (jika ada)
        budget_min, budget_max = self.parse_budget_range_from_text(payload.message)
        
        # 5. RAG Pipeline (Subtask 2)
        docs = await self.retrieve_from_db(
            db=db, 
            user_message=payload.message, 
            wilayah_filter=wilayah_filter,
            top_k=5,
            lat=payload.latitude,
            lng=payload.longitude,
            budget_min=budget_min,
            budget_max=budget_max,
        )
        context = self.build_context(docs)
        
        prompt = self.build_prompt(
            user_message=payload.message,
            context=context,
            history=history,
            wilayah=wilayah,
            latitude=payload.latitude,
            longitude=payload.longitude
        )
        
        answer = await self._generate_gemini_response(prompt, docs)
        if not self._is_answer_grounded(answer, docs, wilayah_filter):
            answer = self._build_grounded_answer(
                docs=docs,
                wilayah=wilayah_filter or wilayah,
                budget_min=budget_min,
                budget_max=budget_max,
            )
        
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
        # wilayah_terdeteksi di DB pakai enum, hanya boleh: Indramayu/Cirebon/Majalengka/Kuningan
        wilayah_to_save = wilayah if wilayah in ("Indramayu", "Cirebon", "Majalengka", "Kuningan") else None
        await self.save_session(
            token=session_token,
            messages=messages,
            wilayah=wilayah_to_save,
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