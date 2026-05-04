import pytest
from httpx import AsyncClient
 
 
@pytest.mark.asyncio
async def test_recommendation_popular_no_auth(client: AsyncClient):
    """Tanpa login, fallback ke mode popular."""
    resp = await client.post("/api/v1/recommendation/", json={
        "wilayah": ["Indramayu"],
        "tipe": "wisata",
        "jumlah": 5,
        "mode": "popular"
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] in ("popular", "personal", "nearby")
    assert "items" in data
 
 
@pytest.mark.asyncio
async def test_recommendation_jumlah_out_of_range(client: AsyncClient):
    resp = await client.post("/api/v1/recommendation/", json={
        "jumlah": 25,   # melebihi 20
        "mode": "popular"
    })
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_planning_basic(client: AsyncClient):
    resp = await client.post("/api/v1/recommendation/planning", json={
        "wilayah": ["Cirebon"],
        "jumlah_hari": 1,
        "jumlah_orang": 2,
        "preferensi": ["Alam"]
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "hari" in data
    assert len(data["hari"]) == 1
 
 
@pytest.mark.asyncio
async def test_planning_hari_out_of_range(client: AsyncClient):
    resp = await client.post("/api/v1/recommendation/planning", json={
        "wilayah": ["Cirebon"],
        "jumlah_hari": 15   # melebihi 14
    })
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_planning_wilayah_empty(client: AsyncClient):
    resp = await client.post("/api/v1/recommendation/planning", json={
        "wilayah": [],
        "jumlah_hari": 2
    })
    assert resp.status_code == 422