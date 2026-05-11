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
GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")


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
        top_k: int = 3,
        lat: float = None,
        lng: float = None
    ) -> list:
        """
        Retrieval dari database PostgreSQL menggunakan FTS dan Filter Wilayah.
        Jika lat & lng tersedia, akan diurutkan berdasarkan jarak terdekat.
        """
        import re
        
        # Clean query
        query_str = re.sub(r'[^\w\s]', '', user_message).strip()
        
        # Jika query kosong (hanya tanya "terdekat"), kita buat query default agar tetap narik data
        if not query_str or query_str.lower() in ["terdekat", "rekomendasi", "wisata"]:
            query_str = "wisata"

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

        # 1. Full Text Search (FTS)
        sql_fts = text(f"""
            SELECT *, ts_rank(fts, websearch_to_tsquery('indonesian', :query)) as rank
            {distance_col}
            FROM v_all_tempat
            WHERE fts @@ websearch_to_tsquery('indonesian', :query)
            {"AND wilayah ILIKE :wilayah" if wilayah_filter else ""}
            ORDER BY {order_clause}
            LIMIT :limit
        """)
        
        params = {"query": query_str, "limit": top_k}
        if wilayah_filter: params["wilayah"] = wilayah_filter
        
        result = await db.execute(sql_fts, params)
        docs = result.fetchall()
        
        # 2. Fallback: Jika FTS sepi, coba ambil data terdekat saja (jika ada koordinat)
        if not docs and lat is not None and lng is not None:
            sql_nearby = text(f"""
                SELECT * {distance_col}
                FROM v_all_tempat
                {"WHERE wilayah ILIKE :wilayah" if wilayah_filter else ""}
                ORDER BY distance ASC
                LIMIT :limit
            """)
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
    async def _generate_gemini_response(self, prompt: str, docs: list = None) -> str:
        """Wrapper async untuk memanggil Gemini API / Mock Fallback"""
        
        from google.api_core.exceptions import ResourceExhausted
        import time
        
        def _call_gemini():
            for attempt in range(3):
                try:
                    response = GEMINI_MODEL.generate_content(prompt)
                    return response.text
                except ResourceExhausted as e:
                    if attempt < 2:  # Retry max 2x
                        wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s
                        print(f"Warning: Quota exhausted, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print("Warning: Gemini quota exhausted. Using mock response for testing.")
                        return ChatbotService._get_mock_fallback(prompt, docs)
                except Exception as e:
                    print(f"Error: Gemini error: {e}")
                    # Jika error selain kuota, tetap coba berikan mock daripada error 500
                    return ChatbotService._get_mock_fallback(prompt, docs)
        
        return await asyncio.to_thread(_call_gemini)

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
        emoji = "🏞️"
        tipe = "wisata"

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
            
            # Validasi Relevansi Ketat:
            # Cari kata unik dari user (yang bukan kata tanya umum)
            ignored_words = ["dimana", "lokasi", "alamat", "wisata", "pantai", "kuliner", "itu", "ada", "apa", "berapa"]
            query_words = [w for w in user_part.split() if len(w) > 2 and w not in ignored_words]
            
            # Jika user tanya spesifik (misal: "labuhan bajo") tapi nggak ada di nama hasil DB, tolak!
            is_relevant = any(w in main_nama for w in query_words) if query_words else True
            
            if not is_relevant:
                header = f"🔍 **Maaf, SITA belum menemukan data yang pas untuk '{user_part_raw.strip()}' di Ciayumajakuning.**"
                items_text = "Mungkin tempat yang kamu cari berada di luar jangkauan SITA atau ada kesalahan pengetikan nama tempat."
            else:
                # Proses Jawaban (Sudah tervalidasi relevan atau intent 'terdekat')
                main_nama_fix = main_doc.get('nama', 'Tempat tersebut')
                main_alamat = main_doc.get('alamat_lengkap', 'wilayah Ciayumajakuning')
                main_maps = main_doc.get('link_google_maps', '#')
                main_dist = main_doc.get('distance')

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

        # Tambahkan Contoh Pertanyaan Relevan di akhir
        suggestions = f"\n\n**Coba tanya SITA hal lain seperti:**\n- \"Rekomendasi wisata alam di Majalengka\"\n- \"Kuliner Nasi Jamblang yang enak di Cirebon\"\n- \"Berapa tiket masuk Waduk Darma?\""

        return f"""{header}

{items_text}

💡 *Tips*: Sebaiknya cek jam operasional atau cuaca sebelum berangkat ke lokasi.

{suggestions}

Ada lagi yang bisa SITA bantu seputar Ciayumajakuning?"""


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
        
        # Prioritaskan wilayah dari text, fallback ke geolokasi, default ke Indramayu
        wilayah = wilayah_text or wilayah_geo or "Indramayu"
        
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
        docs = await self.retrieve_from_db(
            db=db, 
            user_message=payload.message, 
            wilayah_filter=wilayah,
            lat=payload.latitude,
            lng=payload.longitude
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