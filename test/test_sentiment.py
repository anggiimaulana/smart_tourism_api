import pytest
from httpx import AsyncClient
 
 
@pytest.mark.asyncio
async def test_predict_sentiment_model_not_found(client: AsyncClient):
    """Jika model belum tersedia, harus return 503 bukan 500."""
    resp = await client.post("/api/v1/sentiment/predict", json={
        "text": "Tempatnya sangat bagus dan bersih!",
        "model": "indobert",
        "tipe_tempat": "wisata",
        "tempat_kode": "WIS-IDM-001"
    })
    assert resp.status_code in (200, 503)
 
 
@pytest.mark.asyncio
async def test_predict_text_too_short(client: AsyncClient):
    resp = await client.post("/api/v1/sentiment/predict", json={
        "text": "ok",
        "model": "naive_bayes",
        "tipe_tempat": "wisata",
        "tempat_kode": "WIS-IDM-001"
    })
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_predict_batch_limit(client: AsyncClient):
    """Batch melebihi 100 item harus ditolak."""
    items = [{"text": f"Ulasan ke-{i} yang cukup panjang", "model": "naive_bayes",
               "tipe_tempat": "wisata", "tempat_kode": "WIS-IDM-001"} for i in range(101)]
    resp = await client.post("/api/v1/sentiment/predict/batch", json={"items": items})
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_sentiment_summary(client: AsyncClient):
    resp = await client.get("/api/v1/sentiment/summary/Indramayu?tipe_tempat=wisata")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_ulasan" in data
    assert "persen_positif" in data