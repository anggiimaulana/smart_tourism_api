import pytest
from httpx import AsyncClient
 
WISATA_PAYLOAD = {
    "nama": "Pantai Test",
    "wilayah": "Indramayu",
    "kecamatan": "Juntinyuat",
    "harga_tiket_min": 5000,
    "harga_tiket_max": 10000,
    "gratis": False,
    "fasilitas": ["Parkir", "Toilet"],
    "gambar": [],
    "status": "aktif",
}
 
 
@pytest.mark.asyncio
async def test_list_wisata_public(client: AsyncClient):
    resp = await client.get("/api/v1/wisata/")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "items" in resp.json()["data"]
 
 
@pytest.mark.asyncio
async def test_list_wisata_filter_wilayah(client: AsyncClient):
    resp = await client.get("/api/v1/wisata/?wilayah=Indramayu&limit=5")
    assert resp.status_code == 200
 
 
@pytest.mark.asyncio
async def test_create_wisata_requires_admin(client: AsyncClient, user_token: str):
    resp = await client.post("/api/v1/wisata/",
                             json=WISATA_PAYLOAD,
                             headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403
 
 
@pytest.mark.asyncio
async def test_create_wisata_as_admin(client: AsyncClient, admin_token: str):
    resp = await client.post("/api/v1/wisata/",
                             json=WISATA_PAYLOAD,
                             headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "kode" in data
    assert data["nama"] == "Pantai Test"
 
 
@pytest.mark.asyncio
async def test_get_wisata_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/wisata/WIS-XXX-999")
    assert resp.status_code == 404
 
 
@pytest.mark.asyncio
async def test_update_wisata(client: AsyncClient, admin_token: str):
    create = await client.post("/api/v1/wisata/",
                               json={**WISATA_PAYLOAD, "nama": "Pantai Update Test"},
                               headers={"Authorization": f"Bearer {admin_token}"})
    kode = create.json()["data"]["kode"]
    resp = await client.patch(f"/api/v1/wisata/{kode}",
                              json={"deskripsi": "Updated desc"},
                              headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["deskripsi"] == "Updated desc"