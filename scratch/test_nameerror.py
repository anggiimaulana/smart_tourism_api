import asyncio
from app.services.chatbot_service import ChatbotService
from app.schemas.chatbot import ChatRequest
import traceback
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

class FakeDoc:
    def __init__(self, nama):
        self.nama = nama
        self.tipe = "wisata"
        self.wilayah = "Indramayu"
        self.link_google_maps = None
        self.kecamatan = "Test"
        self.alamat = "Test addr"
        self.deskripsi = "Test desc"
        self.harga_min = 0
        self.harga_max = 0
        self.jam_buka = "08:00"
        self.jam_tutup = "17:00"
        self.fasilitas = ""
        self.sentimen_ulasan = ""
        self.rating_google = 4.0

    def keys(self):
        return ["nama", "tipe", "wilayah", "link_google_maps", "kecamatan", "alamat", "deskripsi", "harga_min", "harga_max", "jam_buka", "jam_tutup", "fasilitas", "sentimen_ulasan", "rating_google"]

class MockDB:
    async def execute(self, *args, **kwargs):
        class MockRow:
            def fetchone(self): return None
            def fetchall(self): return [FakeDoc("Test Wisata")]
        return MockRow()
    async def commit(self): pass
    async def rollback(self): pass

class MockPayload:
    message = "buatkan planing liburan di indramayu selama 10 hari dengan budget 1jt"
    session_token = "test"
    latitude = None
    longitude = None
    debug = False

async def test():
    service = ChatbotService()
    # Mock retrieve_from_db to return some docs
    service.retrieve_from_db = lambda *args, **kwargs: asyncio.sleep(0) or [FakeDoc("Test Wisata")]
    try:
        res = await service.ask(MockPayload(), MockDB())
        print("Success:", res.answer)
    except Exception as e:
        traceback.print_exc()

asyncio.run(test())
