"""
Static response templates untuk SITA Chatbot.

Semua jawaban yang TIDAK memerlukan data dari database
didefinisikan di sini agar konsisten dan mudah dikelola.
"""

from __future__ import annotations
import random


def get_identity_response() -> str:
    """Jawaban untuk pertanyaan identitas SITA."""
    return (
        "Halo! 👋 Aku **SITA** (Smart Tourism Information Assistant), "
        "teman jalan-jalan virtualmu untuk menjelajahi wilayah **Ciayumajakuning** "
        "(Cirebon, Indramayu, Majalengka, dan Kuningan), Jawa Barat!\n\n"
        "🎯 **SITA bisa bantuin kamu:**\n"
        "- 🏖️ Nyari rekomendasi tempat wisata hits\n"
        "- 🍜 Berburu kuliner khas daerah yang enak-enak\n"
        "- ☕ Milih tempat nongkrong/cafe yang asik\n"
        "- 📍 Kasih info lokasi, jam buka, tiket, sampai ngerancangin rencana liburanmu (itinerary)\n\n"
        "Yuk ngobrol! Coba aja ketik sesuatu kayak:\n"
        "- \"Tolong dong buatin rencana liburan ke Cirebon 2 hari\"\n"
        "- \"Rekomendasi kuliner legendaris Majalengka\"\n"
        "- \"Tempat nongkrong kekinian di Indramayu\"\n\n"
        "Ada yang bisa SITA bantu sekarang? 😊"
    )


# Beberapa variasi sapaan agar tidak monoton
_GREETING_VARIANTS = [
    (
        "Halo! 👋 Selamat datang di **SITA** — teman jalan-jalanmu di Ciayumajakuning!\n\n"
        "SITA siap nemenin kamu cari info seru tentang:\n"
        "- 🏖️ Tempat wisata kece\n"
        "- 🍜 Kuliner khas yang bikin ngiler\n"
        "- ☕ Tempat nongkrong & cafe hits\n\n"
        "di wilayah **Cirebon, Indramayu, Majalengka, dan Kuningan**.\n\n"
        "Lagi pengen jalan-jalan ke mana nih hari ini? 😊"
    ),
    (
        "Hai! 😄 Seneng banget kamu mampir ke SITA!\n\n"
        "Mau healing, nyari kuliner, atau explore tempat baru di **Ciayumajakuning**? "
        "SITA ada buat bantu kamu nemuin destinasi yang paling pas.\n\n"
        "Cerita dong, lagi pengen nyari apa? 🗺️"
    ),
    (
        "Halo Sobat Jalan! 👋 SITA siap menemanimu!\n\n"
        "Kalau kamu lagi cari rekomendasi wisata, kuliner, atau cafe kekinian "
        "di **Cirebon, Indramayu, Majalengka, atau Kuningan**, tanya SITA aja — "
        "SITA punya banyak info seru buat kamu!\n\n"
        "Mau mulai dari mana? 😊"
    ),
]


def get_greeting_response() -> str:
    """Jawaban untuk sapaan — dipilih secara acak agar tidak monoton."""
    return random.choice(_GREETING_VARIANTS)


def get_thanks_response() -> str:
    """Jawaban untuk ucapan terima kasih."""
    return (
        "Sama-sama! 😊 Seneng banget bisa ngebantu kamu.\n\n"
        "Kalau butuh rekomendasi wisata, kuliner, atau tempat nongkrong "
        "di Ciayumajakuning lagi, jangan sungkan buat ngobrol sama SITA ya!\n\n"
        "Selamat menikmati liburanmu! 🎉"
    )


def get_farewell_response() -> str:
    """Jawaban untuk perpisahan."""
    return (
        "Sampai jumpa! 👋 Semoga infonya ngebantu ya.\n\n"
        "Kalau kapan-kapan pengen jalan-jalan ke Ciayumajakuning lagi, "
        "SITA bakal selalu nungguin di sini! 😊🗺️"
    )


def get_out_of_scope_location_response(detected_location: str | None = None) -> str:
    """Jawaban untuk pertanyaan lokasi di luar Ciayumajakuning."""
    location_text = ""
    if detected_location:
        location_text = f" (terdeteksi: **{detected_location}**)"

    return (
        "🚫 **Maaf, SITA hanya bisa membantu untuk wilayah Ciayumajakuning.**\n\n"
        f"Pertanyaan kamu menyebut lokasi di luar cakupan SITA{location_text}. "
        "SITA hanya memiliki data untuk:\n"
        "- 📍 **Cirebon**\n"
        "- 📍 **Indramayu**\n"
        "- 📍 **Majalengka**\n"
        "- 📍 **Kuningan**\n\n"
        "Coba tanya salah satu ini:\n"
        "- \"Wisata alam terbaik di Kuningan\"\n"
        "- \"Kuliner legendaris Cirebon\"\n"
        "- \"Tempat nongkrong nyaman di Majalengka\"\n\n"
        "Ada yang bisa SITA bantu di wilayah Ciayumajakuning? 😊"
    )


def get_out_of_scope_topic_response(detected_topic: str | None = None) -> str:
    """Jawaban untuk pertanyaan topik di luar pariwisata."""
    topic_text = ""
    if detected_topic and detected_topic != "no_tourism_signal":
        topic_text = f" (terdeteksi topik: *{detected_topic}*)"

    return (
        "🚫 **Maaf, SITA hanya bisa menjawab pertanyaan seputar pariwisata, "
        "kuliner, dan tempat nongkrong di Ciayumajakuning.**\n\n"
        f"Pertanyaan kamu di luar cakupan SITA{topic_text}. "
        "SITA tidak dilatih untuk menjawab topik umum lainnya.\n\n"
        "Yuk, tanya SITA tentang:\n"
        "- \"Rekomendasi wisata alam di Indramayu\"\n"
        "- \"Kuliner khas Majalengka yang wajib dicoba\"\n"
        "- \"Cafe kekinian di Cirebon\"\n\n"
        "Ada yang bisa SITA bantu seputar Ciayumajakuning? 😊"
    )


def get_dangerous_content_response() -> str:
    """Jawaban untuk konten berbahaya/ilegal."""
    return (
        "🚫 **Maaf, SITA tidak bisa membantu permintaan tersebut.**\n\n"
        "SITA adalah asisten pariwisata yang hanya melayani informasi seputar "
        "wisata, kuliner, dan tempat nongkrong di Ciayumajakuning. "
        "Permintaan yang mengandung konten berbahaya tidak dapat diproses.\n\n"
        "🌟 Yuk, tanya SITA hal-hal seru seperti:\n"
        "- \"Rekomendasi pantai di Indramayu\"\n"
        "- \"Cafe kekinian di Cirebon\"\n"
        "- \"Wisata alam terbaik di Kuningan\"\n\n"
        "Ada yang bisa SITA bantu seputar Ciayumajakuning?"
    )


def get_unknown_intent_response() -> str:
    """Jawaban untuk intent yang tidak dikenali."""
    return (
        "🤔 Hmm, maaf ya, SITA kurang paham nih maksud pertanyaan kamu.\n\n"
        "Biar SITA bisa bantu maksimal, coba deh tanyain soal:\n"
        "- 🏖️ **Wisata** — \"Rekomendasi tempat wisata alam di Kuningan\"\n"
        "- 🍜 **Kuliner** — \"Cariin kuliner malam yang enak di Cirebon\"\n"
        "- ☕ **Nongkrong** — \"Cafe kekinian buat nugas di Indramayu\"\n\n"
        "Yuk, coba ceritain lagi pengen nyari apa di Ciayumajakuning? 😊"
    )


def get_no_data_response(wilayah: str | None = None, category: str | None = None) -> str:
    """Jawaban ketika tidak ada data yang cocok di database."""
    scope = wilayah or "Ciayumajakuning"
    cat_text = f" untuk kategori **{category}**" if category else ""

    return (
        f"😔 Yah sayang banget, SITA belum nemu data yang pas{cat_text} "
        f"di **{scope}** buat pertanyaan kamu nih.\n\n"
        "Coba deh:\n"
        "- Ganti kata kunci pencariannya\n"
        "- Intip wilayah lain (Cirebon / Indramayu / Majalengka / Kuningan)\n"
        "- Atau cari kategori lain (wisata / kuliner / nongkrong)\n\n"
        "Ada hal lain yang mau ditanyain ke SITA? 😊"
    )


def build_followup_suggestions(wilayah: str | None = None) -> str:
    """Buat contoh pertanyaan lanjutan yang relevan dengan wilayah aktif."""
    VALID_WILAYAH = ("Indramayu", "Cirebon", "Majalengka", "Kuningan")

    if wilayah and wilayah in VALID_WILAYAH:
        return (
            "\n\n**Coba tanya SITA hal lain seperti:**\n"
            f"- \"Rekomendasi wisata alam di {wilayah}\"\n"
            f"- \"Kuliner khas {wilayah} yang enak\"\n"
            f"- \"Tempat nongkrong yang nyaman di {wilayah}\""
        )

    return (
        "\n\n**Coba tanya SITA hal lain seperti:**\n"
        "- \"Rekomendasi wisata alam di Indramayu\"\n"
        "- \"Kuliner legendaris Cirebon\"\n"
        "- \"Tempat nongkrong nyaman di Kuningan\""
    )