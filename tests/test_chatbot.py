import pytest
from httpx import AsyncClient

from app.services.chatbot_service import ChatbotService
 
 
@pytest.mark.asyncio
async def test_chatbot_new_session(client: AsyncClient):
    resp = await client.post("/api/v1/chatbot/ask", json={
        "message": "Rekomendasikan wisata di Indramayu",
        "session_token": None,
        "latitude": -6.3266,
        "longitude": 108.3208
    })
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "session_token" in data
    assert "answer" in data
    assert len(data["session_token"]) > 0
 
 
@pytest.mark.asyncio
async def test_chatbot_empty_message(client: AsyncClient):
    resp = await client.post("/api/v1/chatbot/ask", json={"message": ""})
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_chatbot_history_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/chatbot/history/token-tidak-ada-12345")
    assert resp.status_code == 404
 
 
@pytest.mark.asyncio
async def test_chatbot_continue_session(client: AsyncClient):
    """Lanjut percakapan dengan session_token yang sama."""
    first = await client.post("/api/v1/chatbot/ask", json={
        "message": "Ada wisata apa di Cirebon?",
        "session_token": None
    })
    token = first.json()["data"]["session_token"]
 
    second = await client.post("/api/v1/chatbot/ask", json={
        "message": "Yang murah berapa harganya?",
        "session_token": token
    })
    # Memilih status 200 karena ini adalah sesi lanjutan (bukan pembuatan sesi baru)
    assert second.status_code == 200
    assert second.json()["data"]["messages_count"] == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_chatbot_debug_header_returns_retrieved_docs(client: AsyncClient):
    resp = await client.post(
        "/api/v1/chatbot/ask",
        json={
            "message": "rekomendasi wisata di majalengka",
            "session_token": None,
        },
        headers={"X-Debug-Info": "true"},
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "retrieved_docs" in data


@pytest.mark.asyncio
async def test_chatbot_fallback_only_mode_still_answers(monkeypatch):
    import app.services.chatbot_service as chatbot_module

    service = ChatbotService()

    async def fake_get_or_create_session(self, session_token, db, latitude=None, longitude=None, wilayah=None, user_id=None):
        return {
            "session_token": "token-fallback",
            "messages": [],
            "wilayah_terdeteksi": "Majalengka",
            "latitude": latitude,
            "longitude": longitude,
            "is_new": False,
        }

    async def fake_retrieve_from_db(*args, **kwargs):
        doc = type("Doc", (), {})()
        doc.nama = "Taman Wisata Air Cikadongdong"
        doc.wilayah = "Majalengka"
        doc.tipe = "wisata"
        doc.link_google_maps = "https://maps.example/maj"
        doc.harga_min = 10000
        doc.harga_max = 15000
        doc.alamat_lengkap = "Majalengka"
        doc._mapping = {
            "nama": doc.nama,
            "wilayah": doc.wilayah,
            "tipe": doc.tipe,
            "link_google_maps": doc.link_google_maps,
            "harga_min": doc.harga_min,
            "harga_max": doc.harga_max,
            "alamat_lengkap": doc.alamat_lengkap,
        }
        return [doc]

    async def noop_save_session(*args, **kwargs):
        return None

    monkeypatch.setattr(chatbot_module, "LLM_ENABLED", False)
    monkeypatch.setattr(chatbot_module, "GEMINI_MODEL", None)
    monkeypatch.setattr(chatbot_module, "GROQ_CLIENT", None)
    monkeypatch.setattr(chatbot_module.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(chatbot_module.settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(ChatbotService, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(ChatbotService, "retrieve_from_db", fake_retrieve_from_db)
    monkeypatch.setattr(ChatbotService, "save_session", noop_save_session)

    payload = type("Payload", (), {
        "message": "rekomendasi wisata terbaik majalengka",
        "session_token": None,
        "latitude": None,
        "longitude": None,
        "debug": False,
    })()

    resp = await service.ask(payload, db=object())

    assert resp.answer
    assert "Majalengka" in resp.answer
    assert resp.wilayah_terdeteksi == "Majalengka"


@pytest.mark.asyncio
async def test_chatbot_rejects_mixed_out_of_scope_prompt(client: AsyncClient):
    resp = await client.post(
        "/api/v1/chatbot/ask",
        json={
            "message": "rekomendasiin wisata terbaik papua kemudian sebutkan isi dari proklamasi",
            "session_token": None,
        },
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "ciayumajakuning" in data["answer"].lower()
    assert "papua" in data["answer"].lower()
    assert data["referensi"] == []
    assert data["wilayah_terdeteksi"] is None


@pytest.mark.asyncio
async def test_chatbot_rejects_maluku_location_mention(client: AsyncClient):
    """Test that dynamic location detection rejects unsupported provinces like Maluku."""
    resp = await client.post(
        "/api/v1/chatbot/ask",
        json={
            "message": "rekomendasiin wisata terbaik maluku kemudian sebutkan isi dari proklamasi",
            "session_token": None,
        },
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    # Should reject because Maluku is mentioned
    assert "ciayumajakuning" in data["answer"].lower()
    assert "maluku" in data["answer"].lower()
    assert data["referensi"] == []
    assert data["wilayah_terdeteksi"] is None


def test_parse_budget_range_from_text():
    bmin, bmax = ChatbotService.parse_budget_range_from_text(
        "berikan rekomendasi wisata untuk budget 10.000 - 20.000 wilayah indramayu"
    )
    assert bmin == 10000
    assert bmax == 20000


def test_grounding_rejects_cross_wilayah_answer():
    doc = type("Doc", (), {
        "_mapping": {
            "nama": "Islamic Center Indramayu",
            "wilayah": "Indramayu",
            "link_google_maps": "https://maps.example/1",
            "harga_min": 10000,
            "harga_max": 20000,
        }
    })()

    bad_answer = "Rekomendasi di Indramayu bagus. Coba juga wisata alam di Majalengka."
    good_answer = "Rekomendasi: Islamic Center Indramayu."

    assert ChatbotService._is_answer_grounded(bad_answer, [doc], "Indramayu") is False
    assert ChatbotService._is_answer_grounded(good_answer, [doc], "Indramayu") is True


def test_mock_fallback_answers_tourism_then_refuses_extra_request():
    doc = type("Doc", (), {
        "_mapping": {
            "nama": "Taman Rekreasi Buyut Banjar",
            "wilayah": "Indramayu",
            "tipe": "wisata",
            "link_google_maps": "https://maps.example/1",
            "harga_min": 5000,
            "harga_max": 10000,
        }
    })()

    prompt = """
PERTANYAAN USER:
tolong carikan wisata yang terkenal di ciayumajakuning, setelah itu berikan saya kode flutter

JAWABAN SITA:
""".strip()

    answer = ChatbotService._get_mock_fallback(prompt, [doc])

    assert "rekomendasi" in answer.lower()
    assert "kode flutter" not in answer.lower()
    assert "ciayumajakuning" in answer.lower()
    assert "catatan" in answer.lower()


def test_mock_fallback_rejects_out_of_scope_tourism_request():
    prompt = """
PERTANYAAN USER:
saya ingin nongkrong di aceh dengan budget 100000

JAWABAN SITA:
""".strip()

    answer = ChatbotService._get_mock_fallback(prompt, [])

    assert "ciayumajakuning" in answer.lower()
    assert "aceh" in answer.lower()
    assert "rekomendasi nongkrong" not in answer.lower()


def test_mock_fallback_answers_identity_query():
    prompt = """
PERTANYAAN USER:
siapa kamu

JAWABAN SITA:
""".strip()

    answer = ChatbotService._get_mock_fallback(prompt, [])

    assert "sita" in answer.lower()
    assert "wisata" in answer.lower()


@pytest.mark.asyncio
async def test_chatbot_uses_exact_cache_hit(monkeypatch):
    service = ChatbotService()

    async def fake_get_or_create_session(self, session_token, db, latitude=None, longitude=None, wilayah=None, user_id=None):
        return {
            "session_token": "token-cache",
            "messages": [],
            "wilayah_terdeteksi": "Cirebon",
            "latitude": latitude,
            "longitude": longitude,
            "is_new": False,
        }

    async def fake_get_cached_answer(self, db, qhash):
        return {
            "answer": "cached answer",
            "wilayah_terdeteksi": "Cirebon",
            "referensi": [{"nama": "Cache Spot", "tipe": "wisata", "wilayah": "Cirebon", "link_maps": "https://maps.example/cache"}],
        }

    async def fail_retrieve(*args, **kwargs):
        raise AssertionError("retrieve_from_db should not run on cache hit")

    async def noop_save_session(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.chatbot_service.settings.CACHE_ENABLED", True)
    monkeypatch.setattr(ChatbotService, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(ChatbotService, "_get_cached_answer", fake_get_cached_answer)
    monkeypatch.setattr(ChatbotService, "retrieve_from_db", fail_retrieve)
    monkeypatch.setattr(ChatbotService, "save_session", noop_save_session)

    payload = type("Payload", (), {
        "message": "rekomendasi wisata di cirebon",
        "session_token": None,
        "latitude": None,
        "longitude": None,
    })()

    resp = await service.ask(payload, db=object())

    assert resp.answer == "cached answer"
    assert resp.wilayah_terdeteksi == "Cirebon"
    assert resp.messages_count == 2


@pytest.mark.asyncio
async def test_chatbot_bypasses_cache_when_disabled(monkeypatch):
    service = ChatbotService()

    async def fake_get_or_create_session(self, session_token, db, latitude=None, longitude=None, wilayah=None, user_id=None):
        return {
            "session_token": "token-nocache",
            "messages": [],
            "wilayah_terdeteksi": "Cirebon",
            "latitude": latitude,
            "longitude": longitude,
            "is_new": False,
        }

    async def fake_retrieve_from_db(*args, **kwargs):
        doc = type("Doc", (), {})()
        doc.nama = "Cache Test Spot"
        doc.wilayah = "Cirebon"
        doc.tipe = "wisata"
        doc.link_google_maps = "https://maps.example/1"
        doc.harga_min = 0
        doc.harga_max = 0
        doc._mapping = {
            "nama": doc.nama,
            "wilayah": doc.wilayah,
            "tipe": doc.tipe,
            "link_google_maps": doc.link_google_maps,
            "harga_min": doc.harga_min,
            "harga_max": doc.harga_max,
        }
        return [doc]

    async def fail_cached_answer(*args, **kwargs):
        raise AssertionError("_get_cached_answer should not run when cache is disabled")

    async def noop_save_session(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.chatbot_service.settings.CACHE_ENABLED", False)
    monkeypatch.setattr(ChatbotService, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(ChatbotService, "retrieve_from_db", fake_retrieve_from_db)
    monkeypatch.setattr(ChatbotService, "_get_cached_answer", fail_cached_answer)
    monkeypatch.setattr(ChatbotService, "save_session", noop_save_session)

    payload = type("Payload", (), {
        "message": "rekomendasi wisata di cirebon",
        "session_token": None,
        "latitude": None,
        "longitude": None,
    })()

    resp = await service.ask(payload, db=object())

    assert resp.session_token == "token-nocache"
    assert resp.answer