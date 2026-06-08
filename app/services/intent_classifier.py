"""
Intent Classifier untuk SITA Chatbot - REVISED VERSION

Klasifikasi intent secara deterministik (tanpa LLM) untuk routing query
sebelum masuk ke RAG pipeline. Ini mencegah query out-of-scope masuk ke DB.
"""

from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# KEYWORD DICTIONARIES
# ══════════════════════════════════════════════════════════════

SUPPORTED_REGIONS = {"cirebon", "indramayu", "majalengka", "kuningan", "ciayumajakuning"}

# --- Identity keywords ---
IDENTITY_KEYWORDS = [
    "siapa kamu", "kamu siapa", "siapa dirimu", "nama kamu", "namamu siapa",
    "apa itu sita", "siapa sita", "kamu itu apa", "kamu apa",
    "siapa nama kamu", "perkenalkan dirimu", "kenalan dong",
    "kamu robot", "kamu ai", "kamu manusia", "kamu bot",
    "untuk apa kamu dibuat", "tujuan kamu apa", "fungsi kamu apa",
    "apa fungsimu", "apa tujuanmu", "kamu bisa apa", "bisa apa kamu",
    "apa yang bisa kamu lakukan", "kemampuan kamu", "fitur kamu",
    "siapa yang membuat kamu", "siapa pembuat kamu", "dibuat oleh siapa",
    "developer kamu siapa", "siapa yang buat kamu", "siapa pencipta kamu",
    "km itu siapa", "kamu sapa", "km sapa", "kamu penciptanya siapa",
    "lu siapa", "elu siapa", "lu sapa",
]

# --- Help / How-to-use keywords ---
HELP_KEYWORDS = [
    "saya harus apa", "bagaimana menggunakannya", "cara pakai",
    "cara menggunakan", "bantu saya", "tolong bantu", "bantuan",
    "panduan", "petunjuk", "apa yang harus saya lakukan",
    "gimana cara pake", "gimana cara pakai", "cara kerjanya gimana",
]

# --- Greeting keywords ---
GREETING_KEYWORDS = [
    "halo", "hai", "hi ", "hello", "hey", "assalamualaikum", "selamat pagi",
    "selamat siang", "selamat sore", "selamat malam", "pagi", "siang",
    "sore", "malam", "met pagi", "met siang", "met sore", "met malam",
    "apa kabar", "gimana kabarmu",
]

# --- Thank you / farewell ---
THANKS_KEYWORDS = [
    "terima kasih", "makasih", "thanks", "thank you", "thx",
    "mantap", "oke terima kasih", "siap terima kasih",
]

FAREWELL_KEYWORDS = [
    "bye", "dadah", "sampai jumpa", "see you", "selamat tinggal",
]

# --- Tourism intent keywords ---
TOURISM_KEYWORDS = [
    "wisata", "pantai", "gunung", "air terjun", "taman", "museum", "candi",
    "danau", "telaga", "curug", "goa", "situ", "waduk", "hutan",
    "kuliner", "restoran", "warung", "masakan", "tempat makan",
    "jajanan", "rumah makan", "bakso", "mie", "nasi", "sate", "empal",
    "nongkrong", "cafe", "kafe", "coffee", "kopi", "ngopi", "hangout",
    "tempat nongkrong", "kedai", "warkop",
    "info wisata", "info kuliner", "info tempat",
    "liburan", "jalan-jalan", "piknik", "vacation", "holiday",
    "destinasi", "tempat hits",
    "tempat kekinian", "tempat instagramable", "spot foto",
    "healing", "staycation", "chill", "refreshing", "cuci mata", "nyantai", "refresh",
    "merekomendasikan", "rekomenin", "rekomendasiin", "nyari", "cari", "mau ke", "pergi ke",
]

# --- Planning / Itinerary keywords ---
PLANNING_KEYWORDS = [
    "planning", "planing", "jadwal", "itinerary", "rencana liburan",
    "rencana wisata", "plan", "susun jadwal", "buatkan rute",
    "buatkan jadwal", "rekomendasi jadwal", "rencana perjalanan",
    "liburan berapa hari", "wisata berapa hari", "mau liburan",
    "perjalanan", "trip",
]

# --- Info specific keywords ---
# CATATAN REVISI: Kata "di" dihapus agar tidak bentrok dengan nama tempat/daerah (cth: "di cirebon")
INFO_SPECIFIC_KEYWORDS = [
    "jam buka", "jam tutup", "jam operasional", "buka jam", "tutup jam",
    "harga tiket", "tiket masuk", "biaya masuk", "berapa harga",
    "dimana", "di mana", "lokasi", "alamat", "rute", "arah",
    "fasilitas", "ada apa aja", "tersedia apa",
    "rating", "review", "ulasan",
]

# --- Dangerous content ---
DANGEROUS_KEYWORDS = [
    "serangan cyber", "cyber attack", "ddos", "hack", "hacking", "hacker",
    "exploit", "malware", "ransomware", "virus komputer", "trojan",
    "phishing", "sql injection", "xss", "brute force",
    "buat bom", "membuat bom", "racun", "senjata", "narkoba", "drugs",
    "bunuh", "membunuh", "pembunuhan", "terorisme", "teroris",
    "pencurian data", "carding", "skimming", "penipuan online",
    "deepfake", "pornografi", "porno", "judi online", "slot online",
]

# --- Irrelevant topics ---
IRRELEVANT_TOPICS = [
    "politik", "presiden", "pemilu", "partai", "pilkada", "gubernur",
    "mentri", "menteri", "pemerintah",
    "agama", "aliran sesat", "kafir", "halal haram",
    "tugas sekolah", "tugas kuliah", "kerjakan pr", "jawab soal",
    "coding", "programming", "python", "javascript", "html", "php",
    "flutter", "dart", "react", "laravel", "mysql", "postgresql", "nodejs", "css", "kode program",
    "matematika", "fisika", "kimia", "sejarah umum", "biologi",
    "harga hp", "handphone", "laptop", "elektronik", "rekomendasi hp",
    "baju", "sepatu", "buku", "obat", "sakit", "rumah sakit",
    "perpustakaan", "sekolah", "kampus", "universitas", "kuliah",
    "pinjol", "pinjaman online", "investasi bodong",
    "pinjam uang", "pinjam duit", "butuh uang", "dana gaib", "pinjem uang",
    "jodoh", "pacar", "mantan", "selingkuh", "nikah",
    "berita terkini", "gosip artis", "selebriti",
    "resep masak", "cara memasak",
    "cara menulis", "cara membuat essay", "cara presentasi",
    "translate", "terjemahkan",
    "proklamasi", "pancasila", "sejarah indonesia", "kemerdekaan",
    "soekarno", "hatta", "isi dari", "sebutkan isi",
    "sistem atm", "atm sederhana",
]

# --- Location: Indonesian provinces & major cities OUTSIDE Ciayumajakuning ---
OUT_OF_SCOPE_PROVINCES = {
    "aceh", "sumatera utara", "sumatera barat", "riau", "jambi",
    "sumatera selatan", "bengkulu", "lampung",
    "kepulauan bangka belitung", "bangka belitung", "kepulauan riau",
    "dki jakarta", "jakarta", "banten",
    "jawa tengah", "yogyakarta", "jogja", "jawa timur",
    "bali", "nusa tenggara barat", "nusa tenggara timur", "ntb", "ntt",
    "kalimantan barat", "kalimantan tengah", "kalimantan selatan",
    "kalimantan timur", "kalimantan utara",
    "sulawesi utara", "sulawesi tengah", "sulawesi selatan",
    "sulawesi tenggara", "sulawesi barat", "gorontalo",
    "maluku", "maluku utara",
    "papua", "papua barat", "papua barat daya", "papua tengah",
    "papua pegunungan", "papua selatan",
}

OUT_OF_SCOPE_CITIES = {
    "jakarta", "surabaya", "bandung", "medan", "semarang", "makassar",
    "palembang", "yogyakarta", "jogja", "malang", "tangerang", "bogor",
    "depok", "bekasi", "pekanbaru", "padang", "batam", "balikpapan",
    "banjarmasin", "manado", "jayapura", "kupang", "mataram", "denpasar",
    "ambon", "ternate", "solo", "surakarta", "samarinda", "pontianak",
    "kendari", "palu", "gorontalo", "jambi", "bengkulu", "pangkalpinang",
    "tanjungpinang", "serang", "cilegon", "tasikmalaya", "garut",
    "sukabumi", "subang", "purwakarta", "karawang",
}

# --- International locations ---
INTERNATIONAL_LOCATIONS = {
    "amerika", "usa", "united states", "inggris", "england", "british",
    "prancis", "france", "paris", "jerman", "germany", "berlin",
    "italia", "italy", "roma", "rome", "spanyol", "spain", "barcelona",
    "madrid", "portugal", "belanda", "netherlands", "amsterdam",
    "rusia", "russia", "moskow", "moscow",
    "china", "tiongkok", "beijing", "shanghai", "guangzhou",
    "jepang", "japan", "tokyo", "osaka", "kyoto",
    "korea", "korea selatan", "seoul", "busan",
    "thailand", "bangkok", "pattaya", "phuket",
    "vietnam", "hanoi", "ho chi minh",
    "singapura", "singapore", "malaysia", "kuala lumpur",
    "filipina", "philippines", "manila",
    "india", "mumbai", "delhi", "new delhi",
    "australia", "sydney", "melbourne",
    "mesir", "egypt", "kairo", "cairo",
    "turki", "turkey", "istanbul",
    "arab saudi", "saudi arabia", "dubai", "abu dhabi",
    "eropa", "europe", "asia tenggara", "afrika", "africa",
    "amerika selatan", "south america", "brazil", "brasil", "argentina", "chile", "peru",
    "kanada", "canada", "meksiko", "mexico",
    "new york", "los angeles", "london", "hawaii",
    "maldives", "maladewa", "swiss", "switzerland",
    "eiffel", "colosseum", "taj mahal", "great wall",
    "niagara", "grand canyon", "santorini", "mykonos",
    "bora bora",
}

# --- Indonesian destinations outside scope ---
OUT_OF_SCOPE_DESTINATIONS = {
    "raja ampat", "labuan bajo", "komodo", "borobudur", "prambanan",
    "bromo", "gunung bromo", "kawah ijen", "ijen", "semeru",
    "tana toraja", "toraja", "bunaken", "wakatobi",
    "derawan", "karimunjawa", "karimun jawa",
    "dieng", "monas", "ancol", "taman mini", "dufan",
    "tangkuban perahu", "kawah putih", "nusa penida",
    "gili trawangan", "gili meno", "gili air",
    "ubud", "kuta", "seminyak", "sanur", "tanah lot",
    "luwatu", "tegallalang",
}


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r'[^\w\s]', '', text.lower())
    t = re.sub(r'\s+', ' ', t).strip()

    aliases = {
        "imy": "indramayu", "imyu": "indramayu", "imkot": "indramayu", "kota mangga": "indramayu",
        "crb": "cirebon", "cerbon": "cirebon", "cirbon": "cirebon", "cebron": "cirebon", "kota udang": "cirebon",
        "kningan": "kuningan", "kng": "kuningan", "kota kuda": "kuningan",
        "maja lengka": "majalengka", "mjk": "majalengka", "kota angin": "majalengka",
    }

    for alias, real_name in aliases.items():
        if alias in t:
            t = re.sub(rf'\b{alias}\b', real_name, t)

    return t


def _text_contains_any(text: str, keywords) -> str | None:
    for kw in keywords:
        if kw in text:
            return kw
    return None


def _has_supported_region(text: str) -> bool:
    for region in SUPPORTED_REGIONS:
        if region in text:
            return True
    return False


def _detect_out_of_scope_location(text: str) -> str | None:
    match = _text_contains_any(text, INTERNATIONAL_LOCATIONS)
    if match:
        return match

    match = _text_contains_any(text, OUT_OF_SCOPE_PROVINCES)
    if match:
        return match

    match = _text_contains_any(text, OUT_OF_SCOPE_CITIES)
    if match:
        return match

    match = _text_contains_any(text, OUT_OF_SCOPE_DESTINATIONS)
    if match:
        return match

    return None


def _extract_duration_days(text: str) -> int:
    """
    Ekstrak durasi perjalanan dari teks user.
    Contoh: "2 hari", "tiga hari", "seminggu" → return angka hari (int).
    Default: 1 jika tidak ditemukan.
    """
    # Cek kata angka tulisan
    word_map = {
        "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
        "enam": 6, "tujuh": 7, "sepekan": 7, "seminggu": 7,
    }
    for word, val in word_map.items():
        if word in text:
            return val

    # Cek angka diikuti "hari" atau "malam"
    match = re.search(r'(\d+)\s*(?:hari|malam|day)', text)
    if match:
        return min(int(match.group(1)), 7)  # cap 7 hari

    return 1  # default 1 hari jika tidak disebutkan


def classify_intent(message: str) -> dict:
    """
    Classify user message intent deterministik.

    Returns dict dengan keys:
      - intent (str)
      - matched_keyword (str | None)
      - has_tourism_intent (bool)
      - detected_location_issue (str | None)
      - durasi_hari (int) — hanya relevan untuk intent "planning"
    """
    normalized = _normalize_text(message)

    result = {
        "intent": "out_of_scope_topic",
        "matched_keyword": None,
        "has_tourism_intent": False,
        "detected_location_issue": None,
        "durasi_hari": 1,
    }

    has_supported = _has_supported_region(normalized)
    has_tourism = any(kw in normalized for kw in TOURISM_KEYWORDS)

    # === PRIORITY 1: Dangerous ===
    match = _text_contains_any(normalized, DANGEROUS_KEYWORDS)
    if match:
        result["intent"] = "dangerous"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 2: Out of scope topic (eksplisit) ===
    match = _text_contains_any(normalized, IRRELEVANT_TOPICS)
    if match:
        result["intent"] = "out_of_scope_topic"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 3: Out-of-scope location ===
    oos_location = _detect_out_of_scope_location(normalized)
    if oos_location and not has_supported:
        result["intent"] = "out_of_scope_location"
        result["matched_keyword"] = oos_location
        result["detected_location_issue"] = oos_location
        return result

    # === PRIORITY 4: Identity ===
    match = _text_contains_any(normalized, IDENTITY_KEYWORDS)
    if match:
        result["intent"] = "identity"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 5: Help ===
    match = _text_contains_any(normalized, HELP_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "identity"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 6: Greeting (hanya jika tidak ada tourism intent) ===
    match = _text_contains_any(normalized, GREETING_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "greeting"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 7: Thanks ===
    match = _text_contains_any(normalized, THANKS_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "thanks"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 8: Farewell ===
    match = _text_contains_any(normalized, FAREWELL_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "farewell"
        result["matched_keyword"] = match
        return result

    # === PRIORITY 9: Planning / Itinerary ===
    match = _text_contains_any(normalized, PLANNING_KEYWORDS)
    if match:
        durasi = _extract_duration_days(normalized)
        result["intent"] = "planning"
        result["matched_keyword"] = match
        result["has_tourism_intent"] = True
        result["durasi_hari"] = durasi
        return result

    # === PRIORITY 10: Info specific ===
    match = _text_contains_any(normalized, INFO_SPECIFIC_KEYWORDS)
    if match and has_tourism:
        result["intent"] = "info_specific"
        result["matched_keyword"] = match
        return result

    # === FINAL GATE: wajib ada tourism signal ===
    is_short = len(normalized.split()) <= 5
    if not has_tourism and not has_supported and not is_short:
        result["intent"] = "out_of_scope_topic"
        result["matched_keyword"] = "no_tourism_signal"
        return result

    # Lolos semua pengecekan → recommendation
    result["intent"] = "recommendation"
    result["has_tourism_intent"] = True
    return result