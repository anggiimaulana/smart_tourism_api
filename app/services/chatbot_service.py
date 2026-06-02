"""Chatbot service template.

Target kerja berdasarkan README:
1. Deteksi wilayah dari pesan atau koordinat pengguna.
2. Ambil konteks relevan dari PostgreSQL Full-Text Search.
3. Susun prompt dan kirim ke Gemini.
4. Simpan percakapan ke chatbot_sessions.
5. Sediakan history dan reset session token.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import logging
from datetime import datetime
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.chatbot import ChatHistoryResponse, ChatRequest, ChatResponse

# Import dari prompts/chatbot_prompts.py
from prompts.chatbot_prompts import (
    SYSTEM_PROMPT,
    MAIN_PROMPT_TEMPLATE,
    FALLBACK_PROMPT,
    format_doc,
    format_lokasi,
)

# Dynamic LLM config from shared DB (Laravel Filament)
from app.services.llm_config_service import get_active_llm_config

# Intent classification & static responses
from app.services.intent_classifier import classify_intent
from app.services.static_responses import (
    get_identity_response,
    get_greeting_response,
    get_thanks_response,
    get_farewell_response,
    get_out_of_scope_location_response,
    get_out_of_scope_topic_response,
    get_dangerous_content_response,
    get_unknown_intent_response,
    get_no_data_response,
    build_followup_suggestions,
)

#  LLM Provider Configuration 
# Support: Gemini (default) atau Groq (fallback/alternatif)
# Set LLM_PROVIDER=groq di .env untuk pakai Groq

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" atau "groq"

# --- Groq Setup ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # atau "llama-3.3-70b-versatile"
GROQ_CLIENT = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        print("Warning: groq package not installed. Run: pip install groq")

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENAI_CLIENT = None

if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        OPENAI_CLIENT = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
    except ImportError:
        print("Warning: openai package not installed. Run: pip install openai")

# --- Gemini Setup ---
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-2.0-flash")
    except Exception:
        GEMINI_MODEL = None

# Do not raise if keys are missing — support working in degraded mode using deterministic
# fallback that relies on DB content. Track whether any LLM provider is available.
LLM_ENABLED = bool(GEMINI_MODEL or GROQ_CLIENT or OPENAI_CLIENT)
logger = logging.getLogger(__name__)
if not LLM_ENABLED:
    logger.warning("No LLM API keys configured or providers unavailable — running in fallback-only mode.")


def get_llm_runtime_status() -> dict:
    return {
        "llm_enabled": LLM_ENABLED,
        "gemini_enabled": bool(GEMINI_MODEL),
        "groq_enabled": bool(GROQ_CLIENT),
        "openai_enabled": bool(OPENAI_CLIENT),
        "provider": LLM_PROVIDER,
    }


# Daftar Provinsi Indonesia (untuk deteksi lokasi out-of-scope)
SUPPORTED_REGIONS = {
    "cirebon", "indramayu", "majalengka", "kuningan", "ciayumajakuning", "jawa barat"
}

INDONESIAN_PROVINCES = {
    "aceh", "sumatera utara", "sumatera barat", "riau", "jambi", "sumatera selatan",
    "bengkulu", "lampung", "kepulauan bangka belitung", "kepulauan riau",
    "jawa barat", "jakarta", "jawa tengah", "yogyakarta", "jawa timur",
    "bali", "nusa tenggara barat", "nusa tenggara timur",
    "kalimantan barat", "kalimantan tengah", "kalimantan selatan", "kalimantan timur", "kalimantan utara",
    "sulawesi utara", "sulawesi tengah", "sulawesi selatan", "sulawesi tenggara", "sulawesi barat",
    "maluku", "maluku utara",
    "papua", "papua barat", "papua barat daya", "papua tengah", "papua pegunungan",
}

MAJOR_INDONESIAN_CITIES = {
    "jakarta", "surabaya", "bandung", "medan", "semarang", "makassar", "palembang",
    "yogyakarta", "malang", "tangerang", "bogor", "depok", "bekasi", "cirebon",
    "pekanbaru", "padang", "batam", "balikpapan", "banjarmasin", "manado", "jayapura",
    "kupang", "mataram", "denpasar", "ambon", "ternate",
}


def _extract_locations_from_text(text: str) -> set:
    """Extract potential location mentions dari text. Return set lokasi (lowercase)."""
    text_lower = text.lower()
    locations = set()
    for prov in INDONESIAN_PROVINCES:
        if prov in text_lower:
            locations.add(prov)
    for city in MAJOR_INDONESIAN_CITIES:
        if city in text_lower:
            locations.add(city)
    return locations


def _is_location_in_supported_region(location: str) -> bool:
    """Check apakah lokasi dalam wilayah Ciayumajakuning."""
    loc_lower = location.lower().strip()
    if loc_lower in SUPPORTED_REGIONS:
        return True
    for supported in SUPPORTED_REGIONS:
        if supported in loc_lower:
            return True
    return False


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
    # SUBTASK 3  Geolokasi & Session Functions
    # ========================================================================

    @staticmethod
    def detect_wilayah_from_text(text: str) -> str | None:
        """
        Subtask 3: Cek keyword Cirebon/Indramayu/Majalengka/Kuningan dalam teks user.
        """
        if not text:
            return None
            
        from app.services.intent_classifier import _normalize_text
        text_norm = _normalize_text(text)
        
        wilayah_list = ["cirebon", "indramayu", "majalengka", "kuningan"]
        for wilayah in wilayah_list:
            if wilayah in text_norm:
                return wilayah.capitalize()
                
        return None

    @staticmethod
    def nearest_wilayah(latitude: float, longitude: float) -> str | None:
        """
        Subtask 3: Hitung haversine ke 4 pusat wilayah  return terdekat.
        
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
    # SUBTASK 2  RAG Pipeline Functions
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
        is_planning: bool = False,
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

        # Clean query  hapus stopwords agar FTS lebih efektif
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
        
        if is_planning:
            tipe_filter = None
            
        # Buat query string dengan OR operator untuk FTS
        if filtered_words:
            # Gunakan regex untuk memastikan hanya mengambil kata kunci yang valid alfanumerik
            valid_words = [re.sub(r'[^\w]', '', w) for w in filtered_words if re.sub(r'[^\w]', '', w)]
            if valid_words:
                query_str = " | ".join(valid_words)
                if is_planning:
                    query_str += " | wisata | kuliner | nongkrong"
            else:
                query_str = "wisata | kuliner | nongkrong"
        else:
            query_str = "wisata | kuliner | nongkrong"
            
        # Double check: jika query_str ternyata kosong atau bermasalah karena glitch karakter
        if not query_str.strip() or query_str.strip() == "|":
            query_str = "wisata | kuliner | nongkrong"

        # Tentukan kolom order (default ranking FTS)
        order_clause = "rank DESC"
        distance_col = ""
        
        # Jika ada koordinat, gunakan formula Haversine untuk hitung jarak (dalam KM)
        # Pastikan koordinat bukan (0,0) yang biasanya merupakan error default GPS
        if lat is not None and lng is not None and (lat != 0.0 or lng != 0.0):
            distance_col = f""", 
                (6371 * acos(
                    cos(radians({lat})) * cos(radians(latitude)) * 
                    cos(radians(longitude) - radians({lng})) + 
                    sin(radians({lat})) * sin(radians(latitude))
                )) AS distance"""
            order_clause = "distance ASC"

        # Build WHERE clause
        where_parts = ["fts @@ to_tsquery('indonesian', :query)"]
        db_limit = 30 if is_planning else top_k
        params = {"query": query_str, "limit": db_limit}
        
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

        # 1. Full Text Search (FTS)  pakai to_tsquery dengan OR
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
            docs = ChatbotService._balance_by_wilayah(docs, db_limit)

        # 6. Distribusi merata antar tipe (wisata, kuliner, nongkrong) jika planning
        if is_planning and docs and len(docs) > 1:
            docs = ChatbotService._balance_by_tipe(docs, top_k)

        return docs[:top_k]

    @staticmethod
    def _balance_by_tipe(docs: list, top_k: int) -> list:
        """Distribusi hasil merata antar tipe (wisata, kuliner, nongkrong)."""
        from collections import defaultdict
        
        by_tipe = defaultdict(list)
        for doc in docs:
            t = getattr(doc, 'tipe', None) or 'wisata'
            by_tipe[t].append(doc)
            
        balanced = []
        # Urutan prioritas: wisata, kuliner, nongkrong
        categories = ["wisata", "kuliner", "nongkrong"]
        pointers = {cat: 0 for cat in categories}
        
        while len(balanced) < top_k:
            added_in_round = False
            for cat in categories:
                if len(balanced) >= top_k:
                    break
                if pointers[cat] < len(by_tipe[cat]):
                    balanced.append(by_tipe[cat][pointers[cat]])
                    pointers[cat] += 1
                    added_in_round = True
            
            if not added_in_round:
                break
                
        return balanced

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
            recent = history[-2:]  #  Optimasi: dikurangi dari 3 ke 2
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

    # ----------------------------
    # CACHING (Exact-match prototype)
    # ----------------------------
    @staticmethod
    def _normalize_query(text: str) -> str:
        """Normalize query for exact-match caching: lowercase, strip punctuation, collapse whitespace."""
        import string
        if not text:
            return ""
        t = text.lower()
        t = t.translate(str.maketrans('', '', string.punctuation))
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _hash_query(normalized: str) -> str:
        import hashlib
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    async def _get_cached_answer(self, db: AsyncSession, session_token: str, qhash: str) -> dict | None:
        try:
            row = await db.execute(
                text("SELECT id, answer, hit_count FROM chatbot_cache WHERE session_token = :token AND query_hash = :qhash"),
                {"token": session_token, "qhash": qhash}
            )
            res = row.fetchone()
            if not res:
                return None
            # increment hit_count
            await db.execute(
                text("UPDATE chatbot_cache SET hit_count = hit_count + 1, updated_at = now() WHERE id = :id"),
                {"id": str(res.id)}
            )
            await db.commit()
            return res.answer
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return None

    async def _save_cache(self, db: AsyncSession, session_token: str, qhash: str, normalized: str, answer_obj: dict) -> None:
        try:
            await db.execute(
                text("""
                INSERT INTO chatbot_cache (id, session_token, query_hash, query_normalized, answer, created_at, updated_at)
                VALUES (:id, :token, :qhash, :normalized, CAST(:answer AS JSONB), now(), now())
                ON CONFLICT (session_token, query_hash) DO UPDATE 
                SET answer = EXCLUDED.answer, updated_at = now(), hit_count = chatbot_cache.hit_count + 1
                """),
                {
                    "id": str(uuid4()),
                    "token": session_token,
                    "qhash": qhash,
                    "normalized": normalized,
                    "answer": json.dumps(answer_obj),
                }
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
            try:
                await db.rollback()
            except Exception:
                pass

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
            return get_no_data_response(wilayah)

        scope = wilayah if wilayah in cls.WILAYAH_LIST else "Ciayumajakuning"

        # Detect dominant category from docs for header label
        tipe_counts = {}
        for doc in docs[:3]:
            d = cls._row_to_dict(doc)
            t = d.get("tipe", "wisata")
            tipe_counts[t] = tipe_counts.get(t, 0) + 1
        dominant_tipe = max(tipe_counts, key=tipe_counts.get) if tipe_counts else "wisata"
        
        tipe_label = {"wisata": "wisata", "kuliner": "kuliner", "nongkrong": "tempat nongkrong"}
        tipe_emoji = {"wisata": "🏖️", "kuliner": "🍜", "nongkrong": "☕"}
        
        # If there are multiple types, use a generic label
        if len(tipe_counts) > 1:
            label = "tempat menarik"
            emoji = "✨"
        else:
            label = tipe_label.get(dominant_tipe, "wisata")
            emoji = tipe_emoji.get(dominant_tipe, "🏖️")

        lines = [f"{emoji} Berikut rekomendasi **{label}** di **{scope}** dari data yang tersedia:"]

        for i, doc in enumerate(docs[:3], 1):
            d = cls._row_to_dict(doc)
            nama = d.get("nama", "-")
            maps = d.get("link_google_maps") or "Tidak tersedia"
            area = d.get("wilayah") or "-"
            alamat = d.get("alamat_lengkap") or d.get("alamat") or "Tidak tersedia"
            jam_buka = d.get("jam_buka") or "?"
            jam_tutup = d.get("jam_tutup") or "?"
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
            deskripsi = (d.get("deskripsi") or "").strip()
            deskripsi_text = f" - {deskripsi[:140]}" if deskripsi else ""
            lines.append(
                f"{i}. **{nama}** ({area})\n"
                f"   - **Lokasi:** {alamat}\n"
                f"   - **Jam buka:** {jam_buka} - {jam_tutup}\n"
                f"   - **Estimasi biaya:** {harga_text}\n"
                f"   - **Maps:** {maps}"
                f"{deskripsi_text}\n"
            )

        lines.append("\nSemua rekomendasi di atas diambil dari data database Smart Tourism.")
        lines.append(build_followup_suggestions(wilayah))
        lines.append("\nAda lagi yang bisa SITA bantu?")
        return "\n".join(lines)

    @classmethod
    def _is_answer_grounded(cls, answer: str, docs: list, wilayah_filter: str | None) -> bool:  
        """
        Validasi jawaban LLM agar tetap terikat pada konteks DB & wilayah target.
        Return False jika terdeteksi halusinasi, keluar wilayah, atau mengklaim data palsu.
        """
        if not answer:
            return False

        lowered = answer.lower()

        # 1. Toleransi untuk jawaban penolakan/data kosong (tidak dianggap halusinasi)
        if any(phrase in lowered for phrase in [
            "maaf", "tidak ditemukan", "belum tersedia", "data belum ada", 
            "coba tanyakan", "belum bisa", "butuh bantuan", "lokasi", "posisi",
            "di luar wilayah", "di luar jangkauan", "tidak melayani", "hanya melayani",
            "tidak memiliki informasi", "tidak ada informasi", "tidak tahu", "tidak dapat"
        ]):
            return True

        # 2. Grounding ke nama tempat dari DB
        if docs:
            doc_names = {
                (cls._row_to_dict(d).get("nama") or "").lower().strip() 
                for d in docs[:5]
            }
            doc_names = {n for n in doc_names if n}
            
            if doc_names:
                # Cek apakah LLM menyebutkan setidaknya SATU nama dari konteks
                # Toleransi: cek substring (LLM biasanya menyebut nama lengkap/paruh)
                has_mention = any(name in lowered for name in doc_names)
                
                # Jika DB punya data tapi LLM tidak menyebut satupun, 
                # kemungkinan halusinasi atau jawaban terlalu umum -> fallback ke deterministic
                if not has_mention:
                    return False

        # 3. Strict Region Scope (Anti Cross-Wilayah)
        if wilayah_filter and wilayah_filter in cls.WILAYAH_LIST:
            target = wilayah_filter.lower()
            for wilayah in cls.WILAYAH_LIST:
                if wilayah.lower() == target:
                    continue
                # Hindari false positive jika kata wilayah muncul di tengah kata lain
                # Gunakan pengecekan dengan spasi atau akhir string untuk akurasi
                if f" {wilayah.lower()} " in lowered or lowered.endswith(f" {wilayah.lower()}"):
                    return False

        return True

    # --- Helper: Async wrapper untuk LLM API (Gemini / Groq / OpenAI) ---
    async def _generate_gemini_response(self, prompt: str, docs: list = None, db: AsyncSession = None) -> str:
        """Wrapper async untuk memanggil LLM API dengan dynamic config dari DB (Filament) atau fallback .env."""

        import time

        # If LLM is not enabled, skip attempts and return mock fallback
        if not LLM_ENABLED:
            logger.info("LLM disabled — trying dynamic config from DB...")

        # 1) Coba dynamic config dari database (diatur via Laravel Filament)
        db_config = None
        if db is not None:
            try:
                db_config = await get_active_llm_config(db)
            except Exception as e:
                logger.warning("Failed to fetch LLM config from DB: %s", e)

        if db_config:
            logger.info("Using dynamic LLM config from DB: provider=%s model=%s", db_config["provider"], db_config["model"])
            result = await asyncio.to_thread(self._call_dynamic_provider, prompt, db_config)
            if result:
                return result
            logger.warning("Dynamic LLM config failed, falling back to env-based providers.")

        # If LLM is disabled (no env keys) AND no DB config, return mock
        if not LLM_ENABLED:
            logger.info("LLM disabled — using deterministic fallback for response.")
            return ChatbotService._get_mock_fallback(prompt, docs)

        # 2) Fallback ke module-level providers (dari .env)
        if LLM_PROVIDER == "openai" and OPENAI_CLIENT:
            providers = [("openai", self._call_openai), ("groq", self._call_groq), ("gemini", self._call_gemini)]
        elif LLM_PROVIDER == "groq" and GROQ_CLIENT:
            providers = [("groq", self._call_groq), ("gemini", self._call_gemini), ("openai", self._call_openai)]
        else:
            providers = [("gemini", self._call_gemini), ("openai", self._call_openai), ("groq", self._call_groq)]

        for provider_name, call_fn in providers:
            logger.info(f"Attempting LLM provider: {provider_name}")
            try:
                result = await asyncio.to_thread(call_fn, prompt)
                if result:
                    logger.info(f"LLM provider {provider_name} returned a response")
                    return result
                else:
                    logger.warning(f"LLM provider {provider_name} returned empty response")
            except Exception as e:
                logger.warning(f"{provider_name} failed: {e}")
                continue

        # Semua provider gagal -> fallback
        logger.warning("All LLM providers failed. Using mock deterministic fallback.")
        return None

    @staticmethod
    def _call_dynamic_provider(prompt: str, config: dict) -> str | None:
        """Call LLM menggunakan konfigurasi dari database (Filament).
        
        config keys: provider, base_url, api_key, model
        """
        provider = config.get("provider", "").lower()
        api_key = config.get("api_key")
        model = config.get("model")
        base_url = config.get("base_url")

        if not api_key:
            logger.warning("Dynamic config has no API key for provider: %s", provider)
            return None

        system_msg = "Kamu adalah SITA, asisten pariwisata Ciayumajakuning. Jawab dalam Bahasa Indonesia dengan ramah dan informatif. Hanya jawab pertanyaan seputar wisata, kuliner, dan tempat nongkrong di wilayah Cirebon, Indramayu, Majalengka, dan Kuningan."

        try:
            if provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=base_url or "https://openrouter.ai/api/v1")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1024,
                )
                return response.choices[0].message.content

            elif provider == "groq":
                from groq import Groq
                client = Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1024,
                )
                return response.choices[0].message.content

            elif provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                gen_model = genai.GenerativeModel(model)
                response = gen_model.generate_content(prompt, generation_config={"max_output_tokens": 2048})
                return response.text

            else:
                logger.warning("Unknown provider in dynamic config: %s", provider)
                return None

        except Exception as e:
            logger.warning("Dynamic LLM call failed (%s): %s", provider, e)
            return None

    @staticmethod
    def _call_gemini(prompt: str) -> str | None:
        """Call Gemini API dengan retry."""
        if not GEMINI_MODEL:
            return None
        
        from google.api_core.exceptions import ResourceExhausted
        import time

        for attempt in range(2):
            try:
                response = GEMINI_MODEL.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": 2048}
                )
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
    def _call_openai(prompt: str) -> str | None:
        """Call OpenAI API."""
        if not OPENAI_CLIENT:
            return None
        
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Kamu adalah SITA, asisten pariwisata Ciayumajakuning. Jawab dalam Bahasa Indonesia dengan ramah dan informatif. Hanya jawab pertanyaan seputar wisata, kuliner, dan tempat nongkrong di wilayah Cirebon, Indramayu, Majalengka, dan Kuningan."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error: OpenAI error: {e}")
            return None

    @staticmethod
    def _get_mock_fallback(prompt: str, docs: list = None, intent: str = "conversational") -> str:
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
        user_part_raw = prompt.split("PERTANYAAN USER:")[-1].split("INSTRUKSI TAMBAHAN:")[0].split("JAWABAN SITA:")[0] if "PERTANYAAN USER:" in prompt else prompt
        user_part = sanitize(user_part_raw)

        tourism_keywords = [
            "wisata", "kuliner", "makan", "makanan", "restoran", "rumah makan",
            "nongkrong", "cafe", "kopi", "coffee", "tempat", "rekomen",
            "rekomendasi", "liburan", "pantai", "gunung", "taman", "museum",
            "jalan-jalan", "jajanan", "mampir",
        ]
        has_tourism_intent = any(k in user_part for k in tourism_keywords)
        mentions_supported_scope = any(
            k in user_part for k in ["ciayumajakuning", "cirebon", "indramayu", "majalengka", "kuningan"]
        )

        # 1. Deteksi wilayah
        wilayah = "wilayah tersebut"
        match = re.search(r"wilayah[:\s]+([A-Za-z\s]+)", prompt, re.IGNORECASE)
        if match: wilayah = match.group(1).strip()
        
        # 2. Ambil data dari docs jika ada
        items = []

        # --- 1. DETEKSI OUT-OF-SCOPE & IRRELEVANT (PRIORITAS UTAMA) ---
        out_of_scope_keywords = [
            "papua", "jayapura", "manokwari", "biak", "raja ampat",
            "jakarta", "bandung", "bogor", "depok", "tangerang", "bekasi",
            "jogja", "yogyakarta", "bali", "lombok", "surabaya", "semarang", "malang",
            "labuan", "labuhan", "bajo", "medan", "makassar", "singapura", "malaysia",
            "monas", "borobudur", "prambanan", "aceh", "jepara", "jepang", "japan",
            "korea", "thailand", "vietnam",
        ]
        
        irrelevant_topics = [
            "politik", "presiden", "agama", "tugas sekolah", "matematika", "rumus", 
            "coding", "programming", "uang", "pinjol", "jodoh", "pacar", "nikah",
            "berita", "gempa", "kriminal", "hantu", "misteri", "siapa penemu", "siapa yang membuat",
            "proklamasi", "pancasila", "sejarah indonesia", "kemerdekaan", "soekarno", "hatta",
            "flutter", "dart", "php", "golang", "typescript", "react", "laravel", "mysql", "postgresql",
            "nodejs", "html", "css", "javascript", "python", "kode program", "sistem atm", "atm sederhana",
            "pinjam uang", "pinjol", "dana gaib", "Butuh uang","pinjam duit"
        ]

        is_out_of_scope = any(k in user_part for k in out_of_scope_keywords)
        is_irrelevant = any(k in user_part for k in irrelevant_topics)

        if any(k in user_part for k in ["siapa kamu", "nama kamu", "siapa dirimu", "apa itu sita", "kamu siapa"]):
            return "Halo! Saya **SITA** (Smart Tourism Information Assistant), asisten virtual pariwisata Ciayumajakuning. Saya bisa bantu kamu cari info wisata, kuliner, atau tempat nongkrong keren!"

        if is_out_of_scope:
            found = next((k for k in out_of_scope_keywords if k in user_part), None)
            found_text = f" tentang {found}" if found else ""
            return (
                " **Maaf, SITA hanya bisa ajudar wilayah Ciayumajakuning (Cirebon, Indramayu, Majalengka, dan Kuningan).**\n\n"
                f"Permintaan kamu menyebut lokasi atau topik di luar cakupan SITA{found_text}, jadi saya tidak bisa memprosesnya.\n\n"
                "Coba tanya salah satu ini:\n"
                "- \"Wisata alam di Kuningan\"\n"
                "- \"Kuliner legendaris Cirebon\"\n"
                "- \"Tempat nongkrong nyaman di Majalengka\""
            )

        restriction_note = ""
        if has_tourism_intent and (is_out_of_scope or is_irrelevant):
            restriction_note = (
                "\n\n **Catatan:** Saya hanya bisa membantu topik wisata, kuliner, dan tempat nongkrong di Ciayumajakuning. "
                "Permintaan lain di luar konteks itu tidak bisa saya bantu."
            )

        if is_out_of_scope and not has_tourism_intent:
            # Non-tourism out-of-scope requests -> reject
            found = next((k for k in out_of_scope_keywords if k in user_part), None)
            found_text = f" terkait {found}" if found else ""
            return f" **Maaf ya, jangkauan informasi SITA saat ini terbatas di wilayah Ciayumajakuning saja.{found_text}**\n\nSITA belum bisa memberikan informasi untuk tempat di luar Cirebon, Indramayu, Majalengka, dan Kuningan. Silakan tanya SITA tentang destinasi di wilayah tersebut ya!"

        if is_irrelevant and not has_tourism_intent:
            return f" **Maaf banget! SITA hanya bisa menjawab pertanyaan seputar pariwisata, kuliner, dan tempat nongkrong.**\n\nSITA tidak dilatih untuk menjawab topik di luar Ciayumajakuning atau topik umum lainnya. Yuk, tanya SITA tentang rekomendasi liburan saja!"

        # --- 2. DETEKSI IDENTITAS & SAPAAN ---
        # C. Cek Intent Lokasi/Alamat/Terdekat
        is_asking_location = any(k in user_part for k in ["dimana", "lokasi", "alamat", "rute", "posisi", "daerah mana"])
        is_asking_nearby = "terdekat" in user_part
        is_asking_price = any(k in user_part for k in ["harga", "biaya", "tiket", "bayar"])

        if intent == "conversational" or (any(k in user_part for k in ["halo", "hai", "pagi", "siang", "sore", "malam"]) and not has_tourism_intent):
            return f"Halo! Ada yang bisa SITA bantu di Ciayumajakuning? Saya punya banyak info tempat wisata, kuliner, dan cafe lokal lho."

        elif docs:
            # Ambil data utama
            main_doc = ChatbotService._row_to_dict(docs[0])
            main_nama = main_doc.get('nama', '').lower()
            
            # Jika FTS sudah return hasil, data dianggap relevan
            # FTS PostgreSQL sudah melakukan filtering relevansi
            is_relevant = True
            
            if not is_relevant:
                header = f" **Maaf, SITA belum menemukan data yang pas untuk '{user_part_raw.strip()}' di Ciayumajakuning.**"
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
                    emoji = ""
                elif tipe == 'nongkrong':
                    emoji = ""
                else:
                    emoji = ""

                if is_asking_nearby:
                    if main_dist is not None:
                        if main_dist <= 10:
                            header = f" Wah, ada yang deket banget nih! **{main_nama_fix}** cuma sekitar {main_dist:.1f} km dari lokasimu."
                        elif main_dist <= 30:
                            header = f" **{main_nama_fix}** adalah yang paling terdekat dari posisimu saat ini (sekitar {main_dist:.1f} km)."
                        else:
                            header = f" Tempat terdekat yang SITA temukan adalah **{main_nama_fix}**, jaraknya sekitar {main_dist:.1f} km. Masih oke buat dikunjungi!"
                    else:
                        header = f" SITA rekomendasikan **{main_nama_fix}** sebagai destinasi terdekat yang populer di {wilayah}."
                    
                    items.append(f"Cek rutenya di sini: {main_maps}")
                    if len(docs) > 1:
                        items.append(f"\nOpsi menarik lainnya:")
                        for d in docs[1:3]:
                            d_extra = ChatbotService._row_to_dict(d)
                            d_dist = d_extra.get('distance')
                            dist_str = f" ({d_dist:.1f} km)" if d_dist else ""
                            items.append(f"- {d_extra.get('nama')}{dist_str} (Maps: {d_extra.get('link_google_maps')})")

                elif is_asking_location:
                    header = f" Tentu! Untuk **{main_nama_fix}**, lokasinya berada di {main_alamat}."
                    items.append(f"Klik di sini untuk rute Maps: {main_maps}")
                elif is_asking_price:
                    h_min = main_doc.get('harga_min', 0)
                    h_max = main_doc.get('harga_max', 0)
                    harga_str = f"Rp{h_min:,} - Rp{h_max:,}" if h_min != h_max else (f"Sekitar Rp{h_min:,}" if h_min > 0 else "Gratis")
                    header = f" Untuk estimasi biaya di **{main_nama_fix}**, siapkan sekitar {harga_str} per orang."
                    items.append(f"Maps: {main_maps}")
                else:
                    header = f"{emoji} Halo! Berikut rekomendasi {tipe} di **{wilayah}** yang mungkin kamu suka:"
                    for d in docs[:3]:
                        d_dict = ChatbotService._row_to_dict(d)
                        items.append(f"**{d_dict.get('nama')}** (Maps: {d_dict.get('link_google_maps')})")
                
                items_text = "\n".join([f"{item}" if item.startswith("-") or item.startswith("\n") else f"{i+1}. {item}" for i, item in enumerate(items)])
        else:
            header = f" **Maaf, SITA belum menemukan data yang cocok.**"
            items_text = "Pastikan tempat yang kamu cari berada di wilayah Cirebon, Indramayu, Majalengka, atau Kuningan."

        # Tambahkan Contoh Pertanyaan Relevan di akhir (sesuai wilayah aktif)
        suggestions = ChatbotService._build_relevant_followup_suggestions(wilayah)

        final_answer = f"""{header}

{items_text}

 *Tips*: Sebaiknya cek jam operasional atau cuaca sebelum berangkat ke lokasi.

{suggestions}

Ada lagi yang bisa SITA bantu seputar Ciayumajakuning?"""

        if restriction_note and has_tourism_intent:
            return final_answer + restriction_note

        return final_answer


    # ========================================================================
    # Content Safety  Tolak pertanyaan berbahaya / di luar konteks
    # ========================================================================

    @staticmethod
    def _check_content_safety(message: str) -> str | None:
        """
        Cek apakah pesan mengandung konten berbahaya atau di luar konteks pariwisata.
        Return pesan penolakan jika terdeteksi, None jika aman.
        """
        import re
        
        msg_lower = re.sub(r'[^\w\s]', '', message).lower()

        # === CHECK 1: Deteksi lokasi yang menyebut provinsi/kota di luar Ciayumajakuning ===
        extracted_locations = _extract_locations_from_text(message)
        unsupported_locations = [loc for loc in extracted_locations if not _is_location_in_supported_region(loc)]
        
        if unsupported_locations:
            first_unsupported = list(unsupported_locations)[0]
            logger.warning(f"Query rejected: unsupported location detected: {first_unsupported}")
            return (
                " **Maaf, jangkauan informasi SITA terbatas di wilayah Ciayumajakuning.**\n\n"
                f"Pertanyaan kamu menyebut lokasi di luar cakupan SITA (yaitu {first_unsupported}). "
                f"SITA hanya bisa memberikan rekomendasi untuk daerah Cirebon, Indramayu, Majalengka, dan Kuningan.\n\n"
                "Coba tanya:\n"
                "- \"Wisata alam di Kuningan\"\n"
                "- \"Pantai terbaik di Indramayu\"\n"
                "- \"Kuliner legendaris Cirebon\""
            )

        # Konten berbahaya / ilegal  HARUS ditolak
        dangerous_keywords = [
            "serangan cyber", "cyber attack", "ddos", "hack", "hacking", "hacker",
            "exploit", "malware", "ransomware", "virus komputer", "trojan",
            "phishing", "sql injection", "xss", "brute force",
            "buat bom", "membuat bom", "racun", "senjata", "narkoba", "drugs",
            "bunuh", "membunuh", "pembunuhan", "terorisme", "teroris",
            "pencurian data", "carding", "skimming", "penipuan online",
            "deepfake", "pornografi", "porno", "judi online", "slot online",
        ]

        # Check dangerous content
        for keyword in dangerous_keywords:
            if keyword in msg_lower:
                return (
                    " **Maaf, SITA tidak bisa membantu permintaan tersebut.**\n\n"
                    "SITA adalah asisten pariwisata yang hanya melayani informasi seputar "
                    "wisata, kuliner, dan tempat nongkrong di Ciayumajakuning. "
                    "Permintaan yang mengandung konten berbahaya atau ilegal tidak dapat diproses.\n\n"
                    " Yuk, tanya SITA hal-hal seru seperti:\n"
                    "- \"Rekomendasi pantai di Indramayu\"\n"
                    "- \"Cafe kekinian di Cirebon\"\n"
                    "- \"Wisata alam terbaik di Kuningan\"\n\n"
                    "Ada yang bisa SITA bantu seputar Ciayumajakuning?"
                )

        return None

        return None  

    # ========================================================================
    # Metode Utama (Menggunakan Subtask 2 & 3)
    # ========================================================================

    async def _build_and_save_response(
        self, payload: ChatRequest, db: AsyncSession, answer: str,
        wilayah: str | None, referensi: list, user_id: str | None = None,
        docs: list = None, debug: bool = False,
    ) -> ChatResponse:
        """Helper: create/get session, save messages, return ChatResponse."""
        session_data = await self.get_or_create_session(
            session_token=payload.session_token, db=db,
            latitude=payload.latitude, longitude=payload.longitude,
            wilayah=wilayah, user_id=user_id,
        )
        session_token = session_data["session_token"]
        history = session_data["messages"]

        messages = list(history)
        messages.append({"role": "user", "content": payload.message, "timestamp": self._timestamp()})
        messages.append({"role": "assistant", "content": answer, "timestamp": self._timestamp()})

        wilayah_to_save = wilayah if wilayah in self.WILAYAH_LIST else None
        await self.save_session(token=session_token, messages=messages, wilayah=wilayah_to_save, db=db)

        retrieved_docs = None
        if (debug or getattr(payload, 'debug', False)) and docs:
            try:
                retrieved_docs = [self._row_to_dict(d) for d in docs]
            except Exception:
                pass

        return ChatResponse(
            session_token=session_token, answer=answer,
            wilayah_terdeteksi=wilayah, referensi=referensi,
            messages_count=len(messages), retrieved_docs=retrieved_docs,
        )

    async def ask(self, payload: ChatRequest, db: AsyncSession, user_id: str | None = None, debug: bool = False) -> ChatResponse:
        """
        Method ask utama dengan arsitektur Intent-First:
        1. Classify intent (deterministic, tanpa LLM)
        2. Route: static intents → static response (TANPA hit DB)
        3. Route: recommendation/info → RAG pipeline
        """
        """
        Method ask utama dengan arsitektur Intent-First
        """
        safety_rejection = self._check_content_safety(payload.message)
        if safety_rejection:
            return await self._build_and_save_response(
                payload, db, safety_rejection, wilayah=None, referensi=[], user_id=user_id,
            )
        # ═══════════════════════════════════════════════════════
        # STEP 1: Intent Classification 
        # ═══════════════════════════════════════════════════════
        intent_result = classify_intent(payload.message)
        intent = intent_result["intent"]
        matched_kw = intent_result.get("matched_keyword")

        logger.info(f"Intent classified: {intent} (keyword: {matched_kw})")

        # ═══════════════════════════════════════════════════════
        # STEP 2: Route static intents (NO DB access)
        # ═══════════════════════════════════════════════════════
        STATIC_INTENT_MAP = {
            "dangerous": get_dangerous_content_response,
            "unknown": get_unknown_intent_response,
        }

        # Jika LLM mati, gunakan static response untuk semuanya
        if not LLM_ENABLED:
            STATIC_INTENT_MAP.update({
                "identity": get_identity_response,
                "greeting": get_greeting_response,
                "thanks": get_thanks_response,
                "farewell": get_farewell_response,
            })

        if intent in STATIC_INTENT_MAP:
            answer = STATIC_INTENT_MAP[intent]()
            return await self._build_and_save_response(
                payload, db, answer, wilayah=None, referensi=[], user_id=user_id,
            )

        if intent == "out_of_scope_location":
            answer = get_out_of_scope_location_response(matched_kw)
            return await self._build_and_save_response(
                payload, db, answer, wilayah=None, referensi=[], user_id=user_id,
            )

        if intent == "out_of_scope_topic":
            answer = get_out_of_scope_topic_response(matched_kw)
            return await self._build_and_save_response(
                payload, db, answer, wilayah=None, referensi=[], user_id=user_id,
            )

        # ═══════════════════════════════════════════════════════
        # STEP 3: Wilayah detection (only for recommendation/info_specific)
        # ═══════════════════════════════════════════════════════
        wilayah_text = self.detect_wilayah_from_text(payload.message)
        wilayah_geo = None
        if payload.latitude and payload.longitude:
            wilayah_geo = self.nearest_wilayah(payload.latitude, payload.longitude)

        msg_lower = payload.message.lower()
        is_all_region = "ciayumajakuning" in msg_lower or "ciayumajakung" in msg_lower

        mentioned_wilayah = [w.capitalize() for w in ["cirebon", "indramayu", "majalengka", "kuningan"] if w in msg_lower]

        if is_all_region or len(mentioned_wilayah) > 1:
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
            wilayah_filter = None
            wilayah = "Ciayumajakuning"

        # ═══════════════════════════════════════════════════════
        # STEP 4: Budget parsing
        # ═══════════════════════════════════════════════════════
        budget_min, budget_max = self.parse_budget_range_from_text(payload.message)

        # ═══════════════════════════════════════════════════════
        # STEP 5: Cache check (SESSION-BASED)
        # ═══════════════════════════════════════════════════════
        normalized = self._normalize_query(payload.message)
        qhash = self._hash_query(normalized)

        # Dapatkan session_token untuk keperluan cache
        session_data_for_cache = await self.get_or_create_session(
            session_token=payload.session_token, db=db,
            latitude=payload.latitude, longitude=payload.longitude,
            wilayah=None, user_id=user_id,
        )
        current_session_token = session_data_for_cache["session_token"]

        if settings.CACHE_ENABLED:
            # Cek cache dengan session_token
            cached = await self._get_cached_answer(db, current_session_token, qhash)
            if cached:
                c_answer = cached.get("answer") if isinstance(cached, dict) else cached["answer"]
                c_wilayah = (cached.get("wilayah_terdeteksi") if isinstance(cached, dict) else None) or wilayah
                c_ref = (cached.get("referensi") if isinstance(cached, dict) else None) or []
                return await self._build_and_save_response(
                    payload, db, c_answer, wilayah=c_wilayah, referensi=c_ref, user_id=user_id,
                )

        # ═══════════════════════════════════════════════════════
        # STEP 6: RAG Pipeline (recommendation / info_specific / planning)
        # ═══════════════════════════════════════════════════════
        is_planning = (intent == "planning")
        top_k_val = 15 if is_planning else 5

        # Contextualize query for RAG retrieval to avoid amnesia
        search_query = payload.message
        history_msgs = session_data_for_cache.get("messages", [])
        if len(history_msgs) >= 2:
            followup_keywords = ["kesana", "ke sana", "disana", "di sana", "tempat itu", "tempat tadi", "tiket", "jam", "buka", "tutup", "lokasi", "harga", "dimana"]
            if any(kw in payload.message.lower() for kw in followup_keywords) or len(payload.message.split()) <= 3:
                last_user_msg = next((m["content"] for m in reversed(history_msgs) if m["role"] == "user"), "")
                if last_user_msg:
                    search_query = f"{last_user_msg} {payload.message}"

        docs = await self.retrieve_from_db(
            db=db, user_message=search_query,
            wilayah_filter=wilayah_filter, top_k=top_k_val,
            lat=payload.latitude, lng=payload.longitude,
            budget_min=budget_min, budget_max=budget_max,
            is_planning=is_planning,
        )

        context = self.build_context(docs) if docs else ""
        session_data = await self.get_or_create_session(
            session_token=payload.session_token, db=db,
            latitude=payload.latitude, longitude=payload.longitude,
            wilayah=wilayah, user_id=user_id,
        )
        prompt = self.build_prompt(
            user_message=payload.message,
            context=context,
            history=session_data["messages"],
            wilayah=wilayah,
            latitude=payload.latitude,
            longitude=payload.longitude
        )
        answer = await self._generate_gemini_response(prompt, docs, db=db)
        
        # Fallback jika LLM gagal total
        is_llm_failed = False
        if answer:
            # Cek apakah jawaban LLM sesuai konteks DB & wilayah (SKIP untuk percakapan biasa)
            # if intent != "conversational" and docs and not self._is_answer_grounded(answer, docs, wilayah_filter):
            # logger.warning("⚠️ LLM answer failed grounding check. Switching to deterministic fallback.")
            # answer = self._build_grounded_answer(docs, wilayah, budget_min, budget_max)
            pass
        else:
            # LLM benar-benar gagal/kosong (Rate Limit / Timeout)
            is_llm_failed = True
            
            # Smart Fallback
            if intent in ["greeting", "identity", "thanks", "farewell"]:
                static_map = {
                    "identity": get_identity_response,
                    "greeting": get_greeting_response,
                    "thanks": get_thanks_response,
                    "farewell": get_farewell_response,
                }
                answer = static_map[intent]()
                docs = []
            elif docs: # Intent terkait pariwisata yang butuh data
                logger.warning("LLM failed. Using deterministic fallback from DB.")
                answer = "*(Sistem sedang sibuk, SITA beralih ke Mode Cepat)*\n\n" + self._build_grounded_answer(docs, wilayah, budget_min, budget_max)
            else:
                answer = "Waduh, maaf banget ya 🙏 Saat ini SITA sedang sibuk melayani Sobat Jalan lainnya (LLM Limit). Coba sapa SITA lagi beberapa saat ya! ✨"
                docs = []

        # Siapkan referensi yang benar-benar disebutkan oleh LLM
        referensi = []
        if docs and answer:
            # Cari doc yang namanya ada di dalam answer
            mentioned_docs = [d for d in docs if (d.nama and d.nama.lower() in answer.lower())]
            
            # Jika tidak ada yang match (misal nama disingkat oleh LLM), gunakan top 5
            if not mentioned_docs:
                mentioned_docs = docs[:5]
                
            # Batasi maksimal 7 referensi
            for d in mentioned_docs[:7]:
                referensi.append({
                    "nama": getattr(d, 'nama', '-'),
                    "tipe": getattr(d, 'tipe', 'wisata'),
                    "wilayah": getattr(d, 'wilayah', ''),
                    "link_maps": getattr(d, 'link_google_maps', None),
                })

        # Save to cache with session_token
        try:
            await self._save_cache(db, current_session_token, qhash, normalized, {
                "answer": answer, "wilayah_terdeteksi": wilayah, "referensi": referensi,
            })
        except Exception:
            pass

        return await self._build_and_save_response(
            payload, db, answer, wilayah=wilayah, referensi=referensi,
            user_id=user_id, docs=docs, debug=debug,
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
