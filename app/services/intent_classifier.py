"""
Intent Classifier untuk SITA Chatbot.

Klasifikasi intent secara deterministik (tanpa LLM) untuk routing query
sebelum masuk ke RAG pipeline. Ini mencegah query out-of-scope masuk ke DB.

Intent yang tersedia:
- identity      : pertanyaan tentang SITA (siapa kamu, dll)
- greeting       : sapaan (halo, hai, dll)
- recommendation : rekomendasi wisata/kuliner/nongkrong
- info_specific  : info detail tempat tertentu
- out_of_scope_location : lokasi di luar Ciayumajakuning
- out_of_scope_topic    : topik non-pariwisata
- dangerous      : konten berbahaya/ilegal
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
    "developer kamu siapa", "siapa yang buat kamu",
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
]

# --- Planning / Itinerary keywords ---
PLANNING_KEYWORDS = [
    "planning", "planing", "jadwal", "itinerary", "rencana liburan",
    "rencana wisata", "plan", "susun jadwal", "buatkan rute",
    "buatkan jadwal", "rekomendasi jadwal", "rencana perjalanan",
]

# --- Info specific keywords ---
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
    "agama", "aliran sesat", "kafir", "halal haram",
    "tugas sekolah", "tugas kuliah", "kerjakan pr", "jawab soal",
    "coding", "programming", "python", "javascript", "html", "php",
    "matematika", "fisika", "kimia", "sejarah umum", "biologi",
    "harga hp", "handphone", "laptop", "elektronik", "rekomendasi hp",
    "baju", "sepatu", "buku", "obat", "sakit", "rumah sakit",
    "perpustakaan", "sekolah", "kampus", "universitas", "kuliah",
    "pinjol", "pinjaman online", "investasi bodong",
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
    # Countries
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
    "amerika selatan", "south america", "brazil", "brasil",
    "kanada", "canada", "meksiko", "mexico",
    "new york", "los angeles", "london", "hawaii",
    "maldives", "maladewa", "swiss", "switzerland",
    # Famous international destinations
    "eiffel", "colosseum", "taj mahal", "great wall",
    "niagara", "grand canyon", "santorini", "mykonos",
    "bora bora", "maldives",
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
    "uluwatu", "tegallalang",
}


def _normalize_text(text: str) -> str:
    """Normalize text: lowercase, strip punctuation, collapse whitespace, and resolve aliases."""
    if not text:
        return ""
    t = re.sub(r'[^\w\s]', '', text.lower())
    t = re.sub(r'\s+', ' ', t).strip()
    
    # Resolve aliases
    aliases = {
        # Indramayu
        "imy": "indramayu", "imyu": "indramayu", "imkot": "indramayu", "kota mangga": "indramayu",
        # Cirebon
        "crb": "cirebon", "cerbon": "cirebon", "cirbon": "cirebon", "cebron": "cirebon", "kota udang": "cirebon",
        # Kuningan
        "kningan": "kuningan", "kng": "kuningan", "kota kuda": "kuningan",
        # Majalengka
        "maja lengka": "majalengka", "mjk": "majalengka", "kota angin": "majalengka",
    }
    
    # Replace whole word aliases
    for alias, real_name in aliases.items():
        if alias in t:
            # use regex to replace whole words only to avoid replacing substrings
            t = re.sub(rf'\b{alias}\b', real_name, t)
            
    return t


def _text_contains_any(text: str, keywords) -> str | None:
    """Check if text contains any keyword. Return the matched keyword or None."""
    for kw in keywords:
        if kw in text:
            return kw
    return None


def _has_supported_region(text: str) -> bool:
    """Check if text explicitly mentions a supported Ciayumajakuning region."""
    for region in SUPPORTED_REGIONS:
        if region in text:
            return True
    return False


def _detect_out_of_scope_location(text: str) -> str | None:
    """
    Detect if user mentions ANY location outside Ciayumajakuning.
    Returns the detected out-of-scope location name, or None if clean.
    """
    # Check international locations
    match = _text_contains_any(text, INTERNATIONAL_LOCATIONS)
    if match:
        return match

    # Check Indonesian provinces outside scope
    match = _text_contains_any(text, OUT_OF_SCOPE_PROVINCES)
    if match:
        return match

    # Check Indonesian cities outside scope
    match = _text_contains_any(text, OUT_OF_SCOPE_CITIES)
    if match:
        return match

    # Check famous destinations outside scope
    match = _text_contains_any(text, OUT_OF_SCOPE_DESTINATIONS)
    if match:
        return match

    return None


def _detect_unknown_location_by_preposition(text: str) -> str | None:
    """
    Fallback: detect unknown locations via preposition patterns.
    Catches 'di finlandia', 'ke kamerun', 'di kamboja', etc. that aren't in any keyword list.
    Only triggers if the word after the preposition is NOT a supported region
    and NOT a generic/common Indonesian word.
    """
    # Common non-location words that follow "di" or "ke" in normal speech
    NON_LOCATION_WORDS = {
        "sini", "sana", "situ", "sana", "mana", "sekitar", "dekat", "atas", "bawah",
        "dalam", "luar", "antara", "samping", "depan", "belakang", "tengah",
        "rumah", "kantor", "sekolah", "kampus", "hotel", "mall",
        "tempat", "area", "wilayah", "daerah", "kawasan", "zona",
        "pagi", "siang", "sore", "malam", "hari", "minggu",
        "wisata", "kuliner", "nongkrong", "cafe", "kafe", "restoran", "warung",
        "pantai", "gunung", "danau", "hutan", "taman", "museum",
        "budget", "bawah", "atas", "sekitar", "antara",
        # Generic adjectives/words
        "sana", "mana", "situ", "sini",
    }

    # Pattern: "di/ke [word]" — extract the word after preposition
    pattern = r'\b(?:di|ke)\s+([a-z]{3,})\b'
    matches = re.findall(pattern, text)

    for loc in matches:
        # Skip supported regions
        if loc in SUPPORTED_REGIONS:
            continue
        # Skip non-location words
        if loc in NON_LOCATION_WORDS:
            continue
        # Skip words that are part of tourism keywords (e.g. "ke pantai")
        if any(loc in kw for kw in TOURISM_KEYWORDS):
            continue
        # Skip very short words or common words
        if len(loc) < 4:
            continue

        # This is likely an unknown location name
        return loc

    return None


def classify_intent(message: str) -> dict:
    """
    Classify user message intent deterministically.
    
    Returns:
        dict with keys:
        - intent: str (identity|greeting|thanks|farewell|recommendation|
                       info_specific|out_of_scope_location|out_of_scope_topic|
                       dangerous|unknown)
        - matched_keyword: str | None
        - has_tourism_intent: bool
        - detected_location_issue: str | None
    """
    normalized = _normalize_text(message)
    
    result = {
        "intent": "unknown",
        "matched_keyword": None,
        "has_tourism_intent": False,
        "detected_location_issue": None,
    }

    has_supported = _has_supported_region(normalized)
    
    # Check tourism intent (used for compound queries)
    has_tourism = _text_contains_any(normalized, TOURISM_KEYWORDS) is not None
    result["has_tourism_intent"] = has_tourism
    
    # === PRIORITY 1: Dangerous content ===
    match = _text_contains_any(normalized, DANGEROUS_KEYWORDS)
    if match:
        result["intent"] = "dangerous"
        result["matched_keyword"] = match
        return result
    
    # === PRIORITY 2: Identity questions ===
    match = _text_contains_any(normalized, IDENTITY_KEYWORDS)
    if match:
        result["intent"] = "identity"
        result["matched_keyword"] = match
        return result
    
    # === PRIORITY 3: Out-of-scope LOCATION (known list) ===
    # If user ALSO mentions a supported region, allow through
    # e.g. "liburan ke cirebon dari jakarta" → destination is cirebon, allow it
    oos_location = _detect_out_of_scope_location(normalized)
    if oos_location and not has_supported:
        result["intent"] = "out_of_scope_location"
        result["matched_keyword"] = oos_location
        result["detected_location_issue"] = oos_location
        return result
    
    # === PRIORITY 4: Out-of-scope TOPIC ===
    match = _text_contains_any(normalized, IRRELEVANT_TOPICS)
    if match:
        if has_tourism and has_supported:
            pass  # Allow — tourism intent in supported region takes priority
        else:
            result["intent"] = "out_of_scope_topic"
            result["matched_keyword"] = match
            return result
    
    # === PRIORITY 5: Pure greeting (no tourism intent) ===
    match = _text_contains_any(normalized, GREETING_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "greeting"
        result["matched_keyword"] = match
        return result
        
    # === PRIORITY 5.5: Help / How-to (no tourism intent) ===
    match = _text_contains_any(normalized, HELP_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "identity" # Route to static identity response which explains how to use SITA
        result["matched_keyword"] = match
        return result
    
    # === PRIORITY 6: Thanks ===
    match = _text_contains_any(normalized, THANKS_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "thanks"
        result["matched_keyword"] = match
        return result
    
    # === PRIORITY 7: Farewell ===
    match = _text_contains_any(normalized, FAREWELL_KEYWORDS)
    if match and not has_tourism:
        result["intent"] = "farewell"
        result["matched_keyword"] = match
        return result
    
    # === PRIORITY 8: Info specific ===
    match = _text_contains_any(normalized, INFO_SPECIFIC_KEYWORDS)
    if match:
        result["intent"] = "info_specific"
        result["matched_keyword"] = match
        return result
        
    # === PRIORITY 8.5: Planning / Itinerary ===
    match = _text_contains_any(normalized, PLANNING_KEYWORDS)
    if match:
        # Planning is a form of tourism intent
        result["intent"] = "planning"
        result["matched_keyword"] = match
        result["has_tourism_intent"] = True
        return result
    
    # (Priority 9 removed: overly aggressive preposition check blocked valid kecamatans)
    
    # === PRIORITY 10: Valid recommendation ===
    if has_tourism:
        result["intent"] = "recommendation"
        result["matched_keyword"] = _text_contains_any(normalized, TOURISM_KEYWORDS)
        return result
    
    # === DEFAULT: fallback to conversational RAG ===
    # Instead of blocking unknown inputs, we route them to the RAG LLM
    # so the bot can maintain natural conversational flow (e.g. answering "di jatibarang" to a follow-up question)
    result["intent"] = "recommendation"
    result["has_tourism_intent"] = True
    return result
