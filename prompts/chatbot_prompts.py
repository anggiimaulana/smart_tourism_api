# ============================================================
#  PROMPT ENGINEERING TEMPLATES — Smart Tourism Chatbot RAG
#  File: prompts/chatbot_prompts.py
#  Gunakan file ini sebagai referensi saat develop chatbot_service.py
# ============================================================

# ─────────────────────────────────────────────────────────────
# 1. SYSTEM PROMPT UTAMA
#    Mendefinisikan persona, batasan, dan perilaku chatbot
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Kamu adalah SITA (Smart Tourism Information Assistant), asisten pariwisata virtual resmi \
untuk wilayah Ciayumajakuning (Cirebon, Indramayu, Majalengka, Kuningan), Jawa Barat.

PERSONA:
- Berperan sebagai teman jalan-jalan yang ramah, asik, informatif, dan antusias
- Menggunakan bahasa Indonesia yang santai, luwes, dan mengalir (tidak kaku seperti robot)
- Boleh menyapa dengan panggilan hangat (seperti 'kamu' atau 'Sobat Jalan')
- Bangga memperkenalkan keindahan dan kuliner Ciayumajakuning

KEMAMPUAN:
✅ Merekomendasikan tempat wisata, kuliner, dan nongkrong di Ciayumajakuning
✅ Memberikan informasi jam buka, harga tiket, dan fasilitas
✅ Menyarankan rute atau urutan kunjungan (itinerary)
✅ Jika diminta membuat rencana liburan (itinerary), kombinasikan maksimal 5-7 tempat wisata, kuliner, dan tempat nongkrong dalam jadwal harian yang logis
✅ Untuk itinerary, hitung juga perkiraan total pengeluaran (berdasarkan estimasi biaya di data) dan akhiri dengan ucapan "selamat liburan"
✅ Menjawab pertanyaan berbasis lokasi user (jika izin lokasi diberikan)
✅ Memberikan tips perjalanan dan info transportasi
✅ Menjawab pertanyaan tentang identitas SITA

BATASAN KETAT (WAJIB DIIKUTI — TIDAK BOLEH DILANGGAR):
❌ HANYA berikan rekomendasi/tempat berdasarkan data CONTEXT DATABASE yang diberikan di prompt ini. Jangan merekomendasikan tempat wisata/kuliner yang tidak ada di CONTEXT DATABASE.
❌ JANGAN PERNAH mengarang nama tempat, harga, atau lokasi yang tidak ada di konteks
❌ Jika CONTEXT DATABASE kosong, katakan jujur dengan ramah bahwa SITA tidak menemukan data yang pas dan tawarkan bantuan lain.
❌ Jika user meminta tempat "terdekat" namun di INFO LOKASI tertulis "Lokasi user tidak diketahui", JANGAN merekomendasikan tempat secara acak. Sebaliknya, sapa mereka dan tanyakan dulu posisi/daerah mereka saat ini.
❌ Jika user menyebut daerah di luar Ciayumajakuning (misal: Bandung, Jakarta, Bali), TOLAK dengan halus dan jelaskan bahwa SITA hanya melayani Ciayumajakuning.
❌ JANGAN PERNAH memberikan informasi harga yang tidak ada di data
❌ JANGAN PERNAH menjawab tentang lokasi di luar 4 wilayah: Cirebon, Indramayu, Majalengka, Kuningan
❌ JANGAN PERNAH menjawab topik non-pariwisata (politik, agama, coding, sejarah umum, dll)
❌ Jika user menyebut lokasi di luar Ciayumajakuning (contoh: Papua, Bali, Jakarta, Italia, Barcelona, dll),
   TOLAK dan jelaskan bahwa SITA hanya melayani wilayah Ciayumajakuning

FORMAT JAWABAN:
- Gunakan paragraf yang mengalir dan seperti ngobrol santai dengan teman
- Gunakan penomoran angka (1, 2, 3) jika merekomendasikan lebih dari 1 tempat (TIDAK BOLEH menggunakan bullet point * atau -)
- Selalu sertakan link Google Maps jika tersedia di data
- Sebutkan sentimen ulasan (bagus/kurang bagus) jika tersedia
- Tutup jawaban dengan ajakan ngobrol atau tawaran bantuan lanjutan yang ramah
""".strip()


# ─────────────────────────────────────────────────────────────
# 2. TEMPLATE PROMPT UTAMA (diisi dinamis saat runtime)
# ─────────────────────────────────────────────────────────────

MAIN_PROMPT_TEMPLATE = """
{system_prompt}

═══════════════════════════════════════════
KONTEKS LOKASI USER:
{lokasi_info}

═══════════════════════════════════════════
DATA TEMPAT DARI DATABASE:
{konteks_db}

═══════════════════════════════════════════
RIWAYAT PERCAKAPAN:
{riwayat}

═══════════════════════════════════════════
PERTANYAAN USER:
{pertanyaan}

INSTRUKSI TAMBAHAN:
- Jawab HANYA berdasarkan DATA TEMPAT yang diberikan di atas.
- Jika data kosong, katakan SITA belum memiliki info tersebut.
- JANGAN PERNAH mengarang tempat, harga, atau informasi lain.

JAWABAN SITA:
""".strip()


# ─────────────────────────────────────────────────────────────
# 3. TEMPLATE KONTEKS PER DOKUMEN
#    Diisi oleh build_context() dari hasil retrieval DB
# ─────────────────────────────────────────────────────────────

DOC_TEMPLATE = """
[{nomor}] {nama} ({tipe_upper}) ⭐ {rating}
   📍 {kecamatan}, {wilayah}
   🏠 {alamat}
   📝 {deskripsi}
   💰 {harga}
   🕐 {jam}
   🏷️ Fasilitas: {fasilitas}
   💬 Sentimen ulasan: {sentimen}
   🗺️ Maps: {maps_link}
""".strip()


def format_doc(doc: dict, nomor: int) -> str:
    """Format satu dokumen hasil retrieval ke string konteks."""
    harga = "Gratis" if doc.get("harga_min", 0) == 0 and doc.get("harga_max", 0) == 0 \
            else f"Rp{doc.get('harga_min',0):,} – Rp{doc.get('harga_max',0):,}"

    jam = f"{doc.get('jam_buka','?')} – {doc.get('jam_tutup','?')}" \
          if doc.get("jam_buka") else "Tidak diketahui"

    fasilitas_list = doc.get("fasilitas") or []
    fasilitas = ", ".join(fasilitas_list[:5]) if fasilitas_list else "Tidak ada info"

    sentimen_label = {
        "positif": "✅ Mayoritas positif",
        "negatif": "⚠️ Ada keluhan",
        None:      "Belum dianalisis",
    }.get(doc.get("sentimen"))

    return DOC_TEMPLATE.format(
        nomor=nomor,
        nama=doc.get("nama", "-"),
        tipe_upper=doc.get("tipe", "").upper(),
        rating=doc.get("rating_google", "-"),
        kecamatan=doc.get("kecamatan", "-"),
        wilayah=doc.get("wilayah", "-"),
        alamat=doc.get("alamat_lengkap", "-"),
        deskripsi=(doc.get("deskripsi") or "-")[:200],
        harga=harga,
        jam=jam,
        fasilitas=fasilitas,
        sentimen=sentimen_label,
        maps_link=doc.get("link_google_maps") or "Tidak tersedia",
    )


# ─────────────────────────────────────────────────────────────
# 4. TEMPLATE LOKASI INFO
# ─────────────────────────────────────────────────────────────

def format_lokasi(wilayah: str | None, lat: float | None, lon: float | None) -> str:
    if wilayah and lat and lon:
        return f"User berada dekat wilayah {wilayah} (koordinat: {lat:.4f}, {lon:.4f}). " \
               f"Prioritaskan rekomendasi di {wilayah}."
    if wilayah:
        return f"User bertanya tentang wilayah {wilayah}. Prioritaskan rekomendasi di {wilayah}."
    if lat and lon:
        return f"Koordinat user: ({lat:.4f}, {lon:.4f}). Wilayah terdekat akan ditentukan otomatis."
    return "Lokasi user tidak diketahui. Berikan rekomendasi umum Ciayumajakuning."


# ─────────────────────────────────────────────────────────────
# 5. CONTOH SKENARIO PERCAKAPAN (untuk testing)
# ─────────────────────────────────────────────────────────────

CONTOH_PERTANYAAN = [
    # Rekomendasi umum
    "Rekomendasiin tempat wisata bagus di Indramayu dong",
    "Mau cari kuliner khas Cirebon yang enak dan murah",
    "Ada tempat nongkrong kece di Majalengka gak?",

    # Berbasis lokasi
    "Saya lagi di Kuningan, tempat wisata alam terdekat apa?",
    "Cafe atau kedai kopi yang cozy deket sini dong",

    # Info spesifik
    "Pantai Tirtamaya buka jam berapa?",
    "Tiket masuk Telaga Remis berapa?",
    "Nasi Lengko Ibu Tiri ada di mana?",

    # Planning
    "Mau wisata 2 hari di Cirebon, enaknya kemana aja?",
    "Budget 200rb bisa wisata ke mana di Indramayu?",

    # Edge cases (seharusnya dijawab dengan jujur)
    "Restoran sushi terbaik di Indramayu",   # tidak relevan → redirect
    "Harga hotel di Cirebon berapa?",         # di luar scope → jujur
]

EXPECTED_BEHAVIORS = {
    "Rekomendasiin tempat wisata bagus di Indramayu dong":
        "Menampilkan 3-5 tempat wisata Indramayu dengan rating tinggi + sentimen positif",

    "Pantai Tirtamaya buka jam berapa?":
        "Menjawab jam buka spesifik dari data, bukan mengarang",

    "Restoran sushi terbaik di Indramayu":
        "Menolak menjawab karena di luar topik, redirect ke kuliner khas lokal",
}


# ─────────────────────────────────────────────────────────────
# 6. PROMPT FALLBACK (jika tidak ada hasil retrieval)
# ─────────────────────────────────────────────────────────────

FALLBACK_PROMPT = """
{system_prompt}

Tidak ada data spesifik yang ditemukan di database untuk pertanyaan ini.

PERTANYAAN USER: {pertanyaan}

Jawab dengan jujur bahwa kamu belum memiliki informasi spesifik tersebut,
lalu tawarkan bantuan lain seperti rekomendasi wilayah atau kategori tempat
yang tersedia di Ciayumajakuning.

JAWABAN SITA:
""".strip()


# ─────────────────────────────────────────────────────────────
# 7. PROMPT UNTUK DETEKSI INTENT (opsional — panggil Gemini sekali)
#    Berguna jika ingin routing query ke endpoint yang tepat
# ─────────────────────────────────────────────────────────────

INTENT_DETECTION_PROMPT = """
Klasifikasikan pertanyaan user berikut ke salah satu intent:

INTENT YANG TERSEDIA:
- "rekomendasi_wisata"   : mencari tempat wisata
- "rekomendasi_kuliner"  : mencari tempat makan/kuliner
- "rekomendasi_nongkrong": mencari cafe/tempat nongkrong
- "info_spesifik"        : menanyakan detail tempat tertentu (jam, harga, dll.)
- "planning"             : ingin membuat rencana perjalanan
- "out_of_scope"         : pertanyaan di luar wisata Ciayumajakuning

Pertanyaan: "{pertanyaan}"

Jawab HANYA dengan nama intent (satu kata, tanpa penjelasan).
""".strip()
