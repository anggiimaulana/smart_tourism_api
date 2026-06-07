"""Chatbot service — Smart Tourism SITA.

Arsitektur Intent-First RAG Pipeline:
1. Classify intent (deterministik, tanpa LLM)
2. Static intents → static response langsung (tanpa hit DB)
3. recommendation / info_specific / planning → RAG pipeline → LLM
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

from prompts.chatbot_prompts import (
    SYSTEM_PROMPT,
    MAIN_PROMPT_TEMPLATE,
    PLANNING_PROMPT_TEMPLATE,
    FALLBACK_PROMPT,
    format_doc,
    format_lokasi,
)

from app.services.llm_config_service import get_active_llm_config
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

# ══════════════════════════════════════════════════════════════
# LLM Provider Setup
# ══════════════════════════════════════════════════════════════

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_CLIENT = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        print("Warning: groq package not installed. Run: pip install groq")

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

import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-2.0-flash")
    except Exception:
        GEMINI_MODEL = None

LLM_ENABLED = bool(GEMINI_MODEL or GROQ_CLIENT or OPENAI_CLIENT)
logger = logging.getLogger(__name__)
if not LLM_ENABLED:
    logger.warning("No LLM API keys configured — running in fallback-only mode.")


def get_llm_runtime_status() -> dict:
    return {
        "llm_enabled": LLM_ENABLED,
        "gemini_enabled": bool(GEMINI_MODEL),
        "groq_enabled": bool(GROQ_CLIENT),
        "openai_enabled": bool(OPENAI_CLIENT),
        "provider": LLM_PROVIDER,
    }


# ══════════════════════════════════════════════════════════════
# Lokasi helpers (module-level, tidak perlu instance)
# ══════════════════════════════════════════════════════════════

INDONESIAN_PROVINCES = {
    "aceh", "sumatera utara", "sumatera barat", "riau", "jambi", "sumatera selatan",
    "bengkulu", "lampung", "kepulauan bangka belitung", "kepulauan riau",
    "jawa barat", "jakarta", "jawa tengah", "yogyakarta", "jawa timur",
    "bali", "nusa tenggara barat", "nusa tenggara timur",
    "kalimantan barat", "kalimantan tengah", "kalimantan selatan",
    "kalimantan timur", "kalimantan utara",
    "sulawesi utara", "sulawesi tengah", "sulawesi selatan",
    "sulawesi tenggara", "sulawesi barat",
    "maluku", "maluku utara",
    "papua", "papua barat", "papua barat daya", "papua tengah", "papua pegunungan",
}

MAJOR_INDONESIAN_CITIES = {
    "jakarta", "surabaya", "bandung", "medan", "semarang", "makassar", "palembang",
    "yogyakarta", "malang", "tangerang", "bogor", "depok", "bekasi",
    "pekanbaru", "padang", "batam", "balikpapan", "banjarmasin", "manado", "jayapura",
    "kupang", "mataram", "denpasar", "ambon", "ternate",
}

SUPPORTED_WILAYAH = {"cirebon", "indramayu", "majalengka", "kuningan"}


def _extract_locations_from_text(text: str) -> set:
    text_lower = text.lower()
    locations = set()
    for prov in INDONESIAN_PROVINCES:
        if prov in text_lower:
            locations.add(prov)
    for city in MAJOR_INDONESIAN_CITIES:
        if city in text_lower:
            locations.add(city)
    return locations


def _is_location_in_supported_region(location: str, supported_regions: set | None = None) -> bool:
    regions = supported_regions or SUPPORTED_WILAYAH
    loc_lower = location.lower().strip()
    if loc_lower in regions:
        return True
    for supported in regions:
        if supported in loc_lower:
            return True
    return False


class ChatbotService:
    """Async service for chatbot workflows using RAG Pipeline."""

    def __init__(self):
        self._wilayah_list = []
        self._supported_regions = set()
    async def _load_regions(self, db: AsyncSession):
        """Memuat data wilayah dari tabel regions agar tidak hardcoded."""
        if self._wilayah_list:
            return
        rows = await db.execute(text("SELECT name FROM regions WHERE is_active = true"))
        regions = [row[0] for row in rows]
        if not regions:
            regions = ["Indramayu", "Cirebon", "Majalengka", "Kuningan"]
        self._wilayah_list = tuple(regions)
        self._supported_regions = {r.lower() for r in regions}
        self._supported_regions.update(["ciayumajakuning", "jawa barat"])

    @staticmethod
    def _timestamp() -> str:
        return datetime.utcnow().isoformat()

    # ════════════════════════════════════════════════════════
    # Budget parsing
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _parse_nominal_to_int(raw: str) -> int | None:
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
        if not text:
            return None, None
        lowered = text.lower()
        pair_match = re.search(
            r"((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)\s*(?:-|sampai|hingga|to)\s*((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)",
            lowered
        )
        if pair_match:
            bmin = cls._parse_nominal_to_int(pair_match.group(1))
            bmax = cls._parse_nominal_to_int(pair_match.group(2))
            if bmin is not None and bmax is not None:
                return (min(bmin, bmax), max(bmin, bmax))
        single_match = re.search(
            r"budget\s*(?:di|sekitar|maks)?\s*((?:rp\s?)?[\d\.,]+\s?(?:rb|k|jt)?)", lowered
        )
        if single_match:
            nominal = cls._parse_nominal_to_int(single_match.group(1))
            if nominal is not None:
                return 0, nominal
        return None, None

    # ════════════════════════════════════════════════════════
    # Geolokasi & Wilayah Detection
    # ════════════════════════════════════════════════════════

    @staticmethod
    def detect_wilayah_from_text(text: str) -> str | None:
        if not text:
            return None
        from app.services.intent_classifier import _normalize_text
        text_norm = _normalize_text(text)
        for wilayah in ["cirebon", "indramayu", "majalengka", "kuningan"]:
            if wilayah in text_norm:
                return wilayah.capitalize()
        return None

    @staticmethod
    def nearest_wilayah(latitude: float, longitude: float) -> str | None:
        if latitude is None or longitude is None:
            return None
        WILAYAH_CENTERS = {
            "Cirebon":   (-6.7063, 108.5571),
            "Indramayu": (-6.3333, 108.3167),
            "Majalengka":(-6.8361, 108.2278),
            "Kuningan":  (-6.9778, 108.4833),
        }
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon / 2) ** 2)
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distances = {w: haversine(latitude, longitude, c[0], c[1]) for w, c in WILAYAH_CENTERS.items()}
        return min(distances, key=distances.get)

    # ════════════════════════════════════════════════════════
    # Session Management
    # ════════════════════════════════════════════════════════

    async def get_or_create_session(
        self,
        session_token: str,
        db: AsyncSession,
        latitude: float | None = None,
        longitude: float | None = None,
        wilayah: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        row = await db.execute(
            text("""
                SELECT session_token, messages, wilayah_terdeteksi, latitude, longitude, user_id
                FROM chatbot_sessions WHERE session_token = :token
            """),
            {"token": session_token},
        )
        existing = row.fetchone()
        if existing:
            if user_id and (not existing.user_id):
                await db.execute(
                    text("UPDATE chatbot_sessions SET user_id = :user_id WHERE session_token = :token"),
                    {"user_id": user_id, "token": existing.session_token},
                )
                await db.commit()
            return {
                "session_token": existing.session_token,
                "messages": list(existing.messages or []),
                "wilayah_terdeteksi": existing.wilayah_terdeteksi or wilayah,
                "latitude": existing.latitude or latitude,
                "longitude": existing.longitude or longitude,
                "is_new": False,
            }
        else:
            new_token = session_token or str(uuid4())
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
                "is_new": True,
            }

    async def save_session(self, token: str, messages: list, wilayah: str | None, db: AsyncSession) -> None:
        await db.execute(
            text("""
                UPDATE chatbot_sessions
                SET messages = CAST(:messages AS jsonb),
                    wilayah_terdeteksi = COALESCE(:wilayah, wilayah_terdeteksi),
                    updated_at = NOW()
                WHERE session_token = :token
            """),
            {"messages": json.dumps(messages), "wilayah": wilayah, "token": token},
        )
        await db.commit()

    # ════════════════════════════════════════════════════════
    # RAG Pipeline — DB Retrieval
    # ════════════════════════════════════════════════════════

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
        import re

        msg_lower = user_message.lower()

        tipe_filter = None
        if not is_planning:
            if any(k in msg_lower for k in ["nongkrong", "cafe", "kafe", "coffee", "kopi", "ngopi", "hangout"]):
                tipe_filter = "nongkrong"
            elif any(k in msg_lower for k in ["kuliner", "makan", "makanan", "restoran", "warung", "masakan", "menu"]):
                tipe_filter = "kuliner"
            elif any(k in msg_lower for k in ["wisata", "pantai", "gunung", "air terjun", "taman", "museum", "candi"]):
                tipe_filter = "wisata"

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

        if filtered_words:
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

        if not query_str.strip() or query_str.strip() == "|":
            query_str = "wisata | kuliner | nongkrong"

        order_clause = "rank DESC"
        distance_col = ""

        if lat is not None and lng is not None and (lat != 0.0 or lng != 0.0):
            distance_col = f""",
                (6371 * acos(
                    cos(radians({lat})) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians({lng})) +
                    sin(radians({lat})) * sin(radians(latitude))
                )) AS distance"""
            order_clause = "distance ASC"

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

        # Fallback 1: hapus tipe filter
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

        # Fallback 2: jika ada koordinat, ambil terdekat
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

        # Distribusi antar wilayah (multi-region query)
        if not wilayah_filter and docs and len(docs) > 1:
            docs = ChatbotService._balance_by_wilayah(docs, db_limit)

        # Distribusi antar tipe (planning)
        if is_planning and docs and len(docs) > 1:
            docs = ChatbotService._balance_by_tipe(docs, top_k)

        return docs[:top_k]

    @staticmethod
    def _balance_by_tipe(docs: list, top_k: int) -> list:
        from collections import defaultdict
        by_tipe = defaultdict(list)
        for doc in docs:
            t = getattr(doc, 'tipe', None) or 'wisata'
            by_tipe[t].append(doc)
        balanced = []
        categories = ["wisata", "kuliner", "nongkrong"]
        pointers = {cat: 0 for cat in categories}
        while len(balanced) < top_k:
            added = False
            for cat in categories:
                if len(balanced) >= top_k:
                    break
                if pointers[cat] < len(by_tipe[cat]):
                    balanced.append(by_tipe[cat][pointers[cat]])
                    pointers[cat] += 1
                    added = True
            if not added:
                break
        return balanced

    @staticmethod
    def _balance_by_wilayah(docs: list, top_k: int) -> list:
        from collections import defaultdict
        by_wilayah = defaultdict(list)
        for doc in docs:
            w = getattr(doc, 'wilayah', None) or 'Unknown'
            by_wilayah[w].append(doc)
        balanced = []
        wilayah_keys = list(by_wilayah.keys())
        idx = 0
        while len(balanced) < top_k and any(by_wilayah.values()):
            key = wilayah_keys[idx % len(wilayah_keys)]
            if by_wilayah[key]:
                balanced.append(by_wilayah[key].pop(0))
            idx += 1
            if idx > top_k * len(wilayah_keys):
                break
        return balanced

    @staticmethod
    def _row_to_dict(row) -> dict:
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        return {col: getattr(row, col, None) for col in row.keys()}

    @staticmethod
    def build_context(docs: list) -> str:
        if not docs:
            return ""
        formatted_docs = [
            format_doc(ChatbotService._row_to_dict(doc), nomor=i)
            for i, doc in enumerate(docs, 1)
        ]
        return "\n\n".join(formatted_docs)

    # ════════════════════════════════════════════════════════
    # Prompt Builder
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _format_history_for_prompt(history: list) -> str:
        """
        Format riwayat percakapan sebagai teks dialog yang mudah dipahami LLM.
        Ambil 10 pesan terakhir (5 giliran user+assistant).
        """
        if not history:
            return "(Belum ada percakapan sebelumnya)"
        recent = history[-10:]
        lines = []
        for h in recent:
            role = "User" if h.get("role") == "user" else "SITA"
            content = h.get("content", "").strip()
            # Batasi panjang tiap pesan di history agar prompt tidak membengkak
            if len(content) > 400:
                content = content[:400] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def build_prompt(
        user_message: str,
        context: str,
        history: list,
        wilayah: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        intent: str = "recommendation",
        durasi_hari: int = 1,
        budget_min: int | None = None,
        budget_max: int | None = None,
    ) -> str:
        """
        Bangun prompt final untuk LLM.
        - Intent planning → PLANNING_PROMPT_TEMPLATE (lebih terarah)
        - Intent lain → MAIN_PROMPT_TEMPLATE
        """
        lokasi_info = format_lokasi(wilayah, latitude, longitude)
        riwayat_text = ChatbotService._format_history_for_prompt(history)

        if intent == "planning" and context:
            # Format info budget
            if budget_min is not None and budget_max is not None:
                budget_info = f"Rp{budget_min:,} – Rp{budget_max:,} per orang"
            elif budget_max is not None:
                budget_info = f"Maksimal Rp{budget_max:,} per orang"
            else:
                budget_info = "Tidak disebutkan (gunakan semua opsi dari data)"

            return PLANNING_PROMPT_TEMPLATE.format(
                system_prompt=SYSTEM_PROMPT,
                durasi_hari=durasi_hari,
                budget_info=budget_info,
                lokasi_info=lokasi_info,
                konteks_db=context,
                riwayat=riwayat_text,
                pertanyaan=user_message,
            )

        if context:
            return MAIN_PROMPT_TEMPLATE.format(
                system_prompt=SYSTEM_PROMPT,
                intent=intent,
                lokasi_info=lokasi_info,
                konteks_db=context,
                riwayat=riwayat_text,
                pertanyaan=user_message,
            )
        else:
            return FALLBACK_PROMPT.format(
                system_prompt=SYSTEM_PROMPT,
                riwayat=riwayat_text,
                pertanyaan=user_message,
            )

    # ════════════════════════════════════════════════════════
    # Caching
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_query(text: str) -> str:
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

    # ════════════════════════════════════════════════════════
    # Deterministic Fallback (dipakai saat LLM gagal total)
    # ════════════════════════════════════════════════════════

    def _build_grounded_answer(
        self,
        docs: list,
        wilayah: str | None,
        budget_min: int | None = None,
        budget_max: int | None = None,
    ) -> str:
        """Jawaban deterministik berbasis DB — bebas halusinasi, dipakai saat LLM down."""
        if not docs:
            return get_no_data_response(wilayah)

        scope = wilayah if wilayah in self._wilayah_list else "Ciayumajakuning"
        tipe_counts = {}
        for doc in docs[:3]:
            d = self._row_to_dict(doc)
            t = d.get("tipe", "wisata")
            tipe_counts[t] = tipe_counts.get(t, 0) + 1
        dominant_tipe = max(tipe_counts, key=tipe_counts.get) if tipe_counts else "wisata"

        tipe_label = {"wisata": "wisata", "kuliner": "kuliner", "nongkrong": "tempat nongkrong"}
        tipe_emoji = {"wisata": "🏖️", "kuliner": "🍜", "nongkrong": "☕"}

        if len(tipe_counts) > 1:
            label, emoji = "tempat menarik", "✨"
        else:
            label = tipe_label.get(dominant_tipe, "wisata")
            emoji = tipe_emoji.get(dominant_tipe, "🏖️")

        lines = [f"{emoji} Berikut rekomendasi **{label}** di **{scope}** dari data yang tersedia:\n"]

        for i, doc in enumerate(docs[:3], 1):
            d = self._row_to_dict(doc)
            nama = d.get("nama", "-")
            maps = d.get("link_google_maps") or "Tidak tersedia"
            alamat = d.get("alamat_lengkap") or d.get("alamat") or "Tidak tersedia"
            jam_buka = d.get("jam_buka") or "?"
            jam_tutup = d.get("jam_tutup") or "?"
            harga_min_val = d.get("harga_min")
            harga_max_val = d.get("harga_max")
            if isinstance(harga_min_val, int) and isinstance(harga_max_val, int):
                if harga_min_val == 0 and harga_max_val == 0:
                    harga_text = "Gratis"
                elif harga_min_val == harga_max_val:
                    harga_text = f"Rp{harga_min_val:,}"
                else:
                    harga_text = f"Rp{harga_min_val:,} - Rp{harga_max_val:,}"
            else:
                harga_text = "Tidak tersedia"
            deskripsi = (d.get("deskripsi") or "").strip()
            deskripsi_text = f"\n   _{deskripsi[:140]}_" if deskripsi else ""

            lines.append(
                f"{i}. **{nama}** ({d.get('wilayah', scope)})\n"
                f"   📍 {alamat}\n"
                f"   🕐 {jam_buka} – {jam_tutup} | 💰 {harga_text}\n"
                f"   🗺️ {maps}"
                f"{deskripsi_text}\n"
            )

        lines.append(build_followup_suggestions(wilayah))
        lines.append("\nAda lagi yang bisa SITA bantu? 😊")
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════
    # LLM Callers
    # ════════════════════════════════════════════════════════

    async def _generate_llm_response(self, prompt: str, docs: list = None, db: AsyncSession = None) -> str | None:
        """
        Wrapper utama pemanggilan LLM.
        Prioritas: DB dynamic config → env-based provider → deterministic fallback.
        """
        # 1. Coba dynamic config dari DB (Filament)
        db_config = None
        if db is not None:
            try:
                db_config = await get_active_llm_config(db)
            except Exception as e:
                logger.warning("Failed to fetch LLM config from DB: %s", e)

        if db_config:
            logger.info("Using dynamic LLM config: provider=%s model=%s", db_config["provider"], db_config["model"])
            result = await asyncio.to_thread(self._call_dynamic_provider, prompt, db_config)
            if result:
                return result
            logger.warning("Dynamic LLM config failed, falling back to env-based providers.")

        if not LLM_ENABLED:
            logger.info("LLM disabled — using deterministic fallback.")
            return None

        # 2. Env-based providers dengan urutan prioritas
        if LLM_PROVIDER == "openai" and OPENAI_CLIENT:
            providers = [("openai", self._call_openai), ("groq", self._call_groq), ("gemini", self._call_gemini)]
        elif LLM_PROVIDER == "groq" and GROQ_CLIENT:
            providers = [("groq", self._call_groq), ("gemini", self._call_gemini), ("openai", self._call_openai)]
        else:
            providers = [("gemini", self._call_gemini), ("openai", self._call_openai), ("groq", self._call_groq)]

        for provider_name, call_fn in providers:
            logger.info("Attempting LLM provider: %s", provider_name)
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(call_fn, prompt),
                    timeout=120.0
                )
                if result:
                    logger.info("LLM provider %s succeeded.", provider_name)
                    return result
                logger.warning("LLM provider %s returned empty response.", provider_name)
            except Exception as e:
                logger.warning("%s failed: %s", provider_name, e)
                continue

        logger.warning("All LLM providers failed.")
        return None

    # Alias lama agar tidak ada breaking change pada pemanggilan eksternal
    _generate_gemini_response = _generate_llm_response

    @staticmethod
    def _call_dynamic_provider(prompt: str, config: dict) -> str | None:
        """
        Call LLM menggunakan konfigurasi dari DB (Filament).
        PERBAIKAN: menggunakan SYSTEM_PROMPT penuh, bukan string pendek.
        """
        provider = config.get("provider", "").lower()
        api_key = config.get("api_key")
        model = config.get("model")
        base_url = config.get("base_url")

        if not api_key:
            logger.warning("Dynamic config has no API key for provider: %s", provider)
            return None

        try:
            if provider in ("openai", "groq"):
                if provider == "openai":
                    from openai import OpenAI
                    client = OpenAI(api_key=api_key, base_url=base_url or "https://openrouter.ai/api/v1")
                else:
                    from groq import Groq
                    client = Groq(api_key=api_key)

                # PENTING: kirim SYSTEM_PROMPT penuh sebagai system message,
                # sisa prompt sebagai user message agar LLM benar-benar mengikuti persona SITA.
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=2048,
                )
                return response.choices[0].message.content

            elif provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                gen_model = genai.GenerativeModel(model)
                # Gemini tidak punya native system role di generate_content,
                # prompt sudah mengandung SYSTEM_PROMPT via template.
                response = gen_model.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": 2048}
                )
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
                    generation_config={"max_output_tokens": 2048},
                    request_options={"timeout": 120.0}
                )
                return response.text
            except ResourceExhausted:
                if attempt < 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning("Gemini quota exhausted.")
                    return None
            except Exception as e:
                logger.error("Gemini error: %s", e)
                return None
        return None

    @staticmethod
    def _call_groq(prompt: str) -> str | None:
        """
        Call Groq API.
        PERBAIKAN: SYSTEM_PROMPT penuh dikirim sebagai system message.
        """
        if not GROQ_CLIENT:
            return None
        try:
            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("Groq error: %s", e)
            return None

    @staticmethod
    def _call_openai(prompt: str) -> str | None:
        """
        Call OpenAI-compatible API.
        PERBAIKAN: SYSTEM_PROMPT penuh dikirim sebagai system message.
        """
        if not OPENAI_CLIENT:
            return None
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("OpenAI error: %s", e)
            return None

    # ════════════════════════════════════════════════════════
    # Grounding Validator
    # ════════════════════════════════════════════════════════

    @classmethod
    def _is_answer_grounded(cls, answer: str, docs: list, wilayah_filter: str | None) -> bool:
        """
        Validasi jawaban LLM agar tetap terikat pada konteks DB & wilayah target.
        Return False jika terdeteksi halusinasi atau keluar wilayah.
        """
        if not answer:
            return False

        lowered = answer.lower()

        # Toleransi untuk jawaban penolakan/data kosong
        if any(phrase in lowered for phrase in [
            "maaf", "tidak ditemukan", "belum tersedia", "data belum ada",
            "coba tanyakan", "belum bisa", "butuh bantuan", "lokasi", "posisi",
            "di luar wilayah", "di luar jangkauan", "tidak melayani", "hanya melayani",
            "tidak memiliki informasi", "tidak ada informasi", "tidak tahu", "tidak dapat",
            "di mana", "dimana", "daerah mana", "sebutkan", "berada"
        ]):
            return True

        # Grounding ke nama tempat dari DB
        if docs:
            doc_names = {
                (cls._row_to_dict(d).get("nama") or "").lower().strip()
                for d in docs[:5]
            }
            doc_names = {n for n in doc_names if n}
            if doc_names and not any(name in lowered for name in doc_names):
                return False

        # Anti cross-wilayah
        wilayah_list = ["Cirebon", "Indramayu", "Majalengka", "Kuningan"]
        if wilayah_filter and wilayah_filter in wilayah_list:
            target = wilayah_filter.lower()
            for wilayah in wilayah_list:
                if wilayah.lower() == target:
                    continue
                if f" {wilayah.lower()} " in lowered or lowered.endswith(f" {wilayah.lower()}"):
                    return False

        return True

    # ════════════════════════════════════════════════════════
    # Content Safety (module-level filter)
    # Hanya untuk lokasi out-of-scope yang lolos classifier.
    # Dangerous content sudah ditangani oleh classify_intent.
    # ════════════════════════════════════════════════════════

    def _check_content_safety(self, message: str) -> str | None:
        """
        Filter tambahan untuk lokasi out-of-scope yang mungkin lolos intent classifier.
        Dangerous content TIDAK dihandle di sini — sudah ditangani oleh classify_intent
        dan di-route ke get_dangerous_content_response().
        """
        extracted_locations = _extract_locations_from_text(message)
        unsupported_locations = [
            loc for loc in extracted_locations
            if not _is_location_in_supported_region(loc, self._supported_regions)
        ]
        if unsupported_locations:
            first = list(unsupported_locations)[0]
            logger.warning("Query rejected: unsupported location: %s", first)
            return get_out_of_scope_location_response(first)
        return None

    # ════════════════════════════════════════════════════════
    # Response Builder & Session Save
    # ════════════════════════════════════════════════════════

    def _build_relevant_followup_suggestions(self, wilayah: str | None) -> str:
        target = wilayah if wilayah in self._wilayah_list else "Ciayumajakuning"
        if target in self._wilayah_list:
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

    async def _build_and_save_response(
        self,
        payload: ChatRequest,
        db: AsyncSession,
        answer: str,
        wilayah: str | None,
        referensi: list,
        user_id: str | None = None,
        docs: list = None,
        debug: bool = False,
    ) -> ChatResponse:
        session_data = await self.get_or_create_session(
            session_token=payload.session_token, db=db,
            latitude=payload.latitude, longitude=payload.longitude,
            wilayah=wilayah, user_id=user_id,
        )
        session_token = session_data["session_token"]
        history = session_data["messages"]
        messages = list(history)

        # Pengingat feedback setiap kelipatan 10 pesan
        if len(messages) > 0 and len(messages) % 10 == 0:
            answer += "\n\n*(Sobat Jalan, kalau jawaban SITA ngebantu, jangan lupa berikan penilaian di bawah ya! 👍)*"

        messages.append({"role": "user", "content": payload.message, "timestamp": self._timestamp()})
        messages.append({"role": "assistant", "content": answer, "timestamp": self._timestamp()})

        wilayah_to_save = wilayah if wilayah in self._wilayah_list else None
        await self.save_session(token=session_token, messages=messages, wilayah=wilayah_to_save, db=db)

        retrieved_docs = None
        if (debug or getattr(payload, 'debug', False)) and docs:
            try:
                retrieved_docs = [self._row_to_dict(d) for d in docs]
            except Exception:
                pass

        return ChatResponse(
            session_token=session_token,
            answer=answer,
            wilayah_terdeteksi=wilayah,
            referensi=referensi,
            messages_count=len(messages),
            retrieved_docs=retrieved_docs,
        )

    # ════════════════════════════════════════════════════════
    # METHOD UTAMA — ask()
    # ════════════════════════════════════════════════════════

    async def ask(
        self,
        payload: ChatRequest,
        db: AsyncSession,
        user_id: str | None = None,
        debug: bool = False,
    ) -> ChatResponse:
        """
        Method ask utama dengan arsitektur Intent-First RAG:
        1. Classify intent (deterministik, tanpa LLM)
        2. Route static intents → static response (tanpa hit DB)
        3. Route recommendation / info_specific / planning → RAG → LLM
        """
        await self._load_regions(db)

        # ─── STEP 1: Content Safety (filter lokasi out-of-scope) ──────────
        # Dangerous content sudah dihandle di classify_intent (PRIORITY 1)
        safety_rejection = self._check_content_safety(payload.message)
        if safety_rejection:
            return await self._build_and_save_response(
                payload, db, safety_rejection, wilayah=None, referensi=[], user_id=user_id,
            )

        # ─── STEP 2: Intent Classification ────────────────────────────────
        intent_result = classify_intent(payload.message)
        intent = intent_result["intent"]
        matched_kw = intent_result.get("matched_keyword")
        durasi_hari = intent_result.get("durasi_hari", 1)

        logger.info("Intent classified: %s (keyword: %s)", intent, matched_kw)

        # ─── STEP 3: Intercept "terdekat" tanpa lokasi ─────────────────────
        if payload.latitude is None and payload.longitude is None:
            msg_lower = payload.message.lower()
            if any(k in msg_lower for k in ["terdekat", "dekat sini", "sekitar sini"]):
                answer = (
                    "Halo Sobat Jalan! 🙋‍♀️\n\n"
                    "SITA belum tahu posisimu saat ini nih. Biar rekomendasinya tepat sasaran, "
                    "kamu lagi berada di daerah atau kecamatan mana sekarang? 📍"
                )
                return await self._build_and_save_response(
                    payload, db, answer, wilayah=None, referensi=[], user_id=user_id,
                )

        # ─── STEP 4: Static intents → langsung return, tanpa DB ───────────
        STATIC_INTENT_MAP = {
            "identity":     get_identity_response,
            "greeting":     get_greeting_response,
            "thanks":       get_thanks_response,
            "farewell":     get_farewell_response,
            "dangerous":    get_dangerous_content_response,
            "unknown":      get_unknown_intent_response,
            "conversational": get_unknown_intent_response,
        }

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

        # ─── STEP 5: Wilayah detection ─────────────────────────────────────
        wilayah_text = self.detect_wilayah_from_text(payload.message)
        wilayah_geo = None
        if payload.latitude and payload.longitude:
            wilayah_geo = self.nearest_wilayah(payload.latitude, payload.longitude)

        msg_lower = payload.message.lower()
        is_all_region = "ciayumajakuning" in msg_lower or "ciayumajakung" in msg_lower
        mentioned_wilayah = [
            w.capitalize() for w in ["cirebon", "indramayu", "majalengka", "kuningan"]
            if w in msg_lower
        ]

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

        # ─── STEP 6: Budget parsing ────────────────────────────────────────
        budget_min, budget_max = self.parse_budget_range_from_text(payload.message)

        # ─── STEP 7: Cache check ───────────────────────────────────────────
        normalized = self._normalize_query(payload.message)
        qhash = self._hash_query(normalized)

        session_data_for_cache = await self.get_or_create_session(
            session_token=payload.session_token, db=db,
            latitude=payload.latitude, longitude=payload.longitude,
            wilayah=None, user_id=user_id,
        )
        current_session_token = session_data_for_cache["session_token"]
        history_msgs = session_data_for_cache.get("messages", [])

        # Cache hanya untuk non-planning (planning terlalu kontekstual untuk di-cache agresif)
        if settings.CACHE_ENABLED and intent != "planning":
            cached = await self._get_cached_answer(db, current_session_token, qhash)
            if cached:
                c_answer = cached.get("answer") if isinstance(cached, dict) else cached["answer"]
                c_wilayah = (cached.get("wilayah_terdeteksi") if isinstance(cached, dict) else None) or wilayah
                c_ref = (cached.get("referensi") if isinstance(cached, dict) else None) or []
                return await self._build_and_save_response(
                    payload, db, c_answer, wilayah=c_wilayah, referensi=c_ref, user_id=user_id,
                )

        # ─── STEP 8: RAG Pipeline ──────────────────────────────────────────
        is_planning = (intent == "planning")
        # Planning butuh lebih banyak dokumen; info_specific cukup 5
        top_k_val = (durasi_hari * 6) if is_planning else 5

        # Contextualize query untuk follow-up pendek
        search_query = payload.message
        followup_keywords = [
            "kesana", "ke sana", "disana", "di sana", "tempat itu", "tempat tadi",
            "tiket", "jam", "buka", "tutup", "lokasi", "harga", "dimana", "itu",
        ]
        if len(history_msgs) >= 2 and (
            any(kw in payload.message.lower() for kw in followup_keywords)
            or len(payload.message.split()) <= 4
        ):
            last_user_msg = next(
                (m["content"] for m in reversed(history_msgs) if m["role"] == "user"), ""
            )
            if last_user_msg:
                search_query = f"{last_user_msg} {payload.message}"
                logger.info("Follow-up query contextualized: %s", search_query[:80])

        docs = await self.retrieve_from_db(
            db=db,
            user_message=search_query,
            wilayah_filter=wilayah_filter,
            top_k=top_k_val,
            lat=payload.latitude,
            lng=payload.longitude,
            budget_min=budget_min,
            budget_max=budget_max,
            is_planning=is_planning,
        )

        # ─── STEP 9: Bangun prompt & panggil LLM ──────────────────────────
        # PERBAIKAN: info_specific sekarang juga lewat LLM (bukan mock)
        # agar jawaban tetap mengalir dengan gaya SITA
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
            longitude=payload.longitude,
            intent=intent,
            durasi_hari=durasi_hari,
            budget_min=budget_min,
            budget_max=budget_max,
        )

        answer = await self._generate_llm_response(prompt, docs, db=db)

        # ─── STEP 10: Fallback jika LLM gagal total ────────────────────────
        if not answer:
            logger.warning("LLM failed. Using deterministic fallback.")
            if intent in ["greeting", "identity", "thanks", "farewell"]:
                static_map = {
                    "identity": get_identity_response,
                    "greeting": get_greeting_response,
                    "thanks": get_thanks_response,
                    "farewell": get_farewell_response,
                }
                answer = static_map[intent]()
                docs = []
            elif docs:
                answer = "*(SITA sedang sibuk, beralih ke Mode Cepat)* 🚀\n\n" + self._build_grounded_answer(
                    docs, wilayah, budget_min, budget_max
                )
            else:
                answer = (
                    "Waduh, maaf banget ya 🙏 SITA lagi sibuk melayani banyak Sobat Jalan nih. "
                    "Coba sapa SITA lagi sebentar ya! ✨"
                )
                docs = []

        # ─── STEP 11: Susun referensi ──────────────────────────────────────
        referensi = []
        if docs and answer:
            mentioned_docs = [d for d in docs if (d.nama and d.nama.lower() in answer.lower())]
            if not mentioned_docs:
                mentioned_docs = docs[:5]
            for d in mentioned_docs[:7]:
                referensi.append({
                    "nama": getattr(d, 'nama', '-'),
                    "tipe": getattr(d, 'tipe', 'wisata'),
                    "wilayah": getattr(d, 'wilayah', ''),
                    "link_maps": getattr(d, 'link_google_maps', None),
                })

        # ─── STEP 12: Simpan ke cache ──────────────────────────────────────
        if intent != "planning":
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

    # ════════════════════════════════════════════════════════
    # Legacy helper — tetap dipertahankan untuk backward compat
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _detect_wilayah(message: str, latitude: float | None, longitude: float | None) -> str | None:
        lower = message.lower()
        wilayah_map = {
            "indramayu": "Indramayu", "cirebon": "Cirebon",
            "majalengka": "Majalengka", "kuningan": "Kuningan",
        }
        for keyword, wilayah in wilayah_map.items():
            if keyword in lower:
                return wilayah
        if latitude is not None and longitude is not None:
            return "Indramayu"
        return None

    # ════════════════════════════════════════════════════════
    # History & Session API
    # ════════════════════════════════════════════════════════

    async def get_history(self, session_token: str, db: AsyncSession) -> ChatHistoryResponse:
        row = await db.execute(
            text("""
                SELECT session_token, messages, wilayah_terdeteksi, created_at
                FROM chatbot_sessions WHERE session_token = :token
            """),
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