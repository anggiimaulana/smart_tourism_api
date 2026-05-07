import pytest
from httpx import AsyncClient
 
 
@pytest.mark.asyncio
async def test_chatbot_new_session(client: AsyncClient):
    resp = await client.post("/api/v1/chatbot/ask", json={
        "message": "Rekomendasikan wisata di Indramayu",
        "session_token": None,
        "latitude": -6.3266,
        "longitude": 108.3208
    })
    assert resp.status_code == 200
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
    assert second.status_code == 200
    assert second.json()["data"]["messages_count"] == 4  # 2 user + 2 assistant