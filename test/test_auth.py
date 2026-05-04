import pytest
from httpx import AsyncClient
 
 
@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "nama": "Budi Santoso",
        "email": "budi@test.com",
        "password": "Budi1234"
    })
    assert resp.status_code == 201
    assert resp.json()["success"] is True
 
 
@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"nama": "A", "email": "dup@test.com", "password": "Dup01234"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
 
 
@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "nama": "A", "email": "weak@test.com", "password": "abc"
    })
    assert resp.status_code == 422
 
 
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "nama": "Login Test", "email": "login@test.com", "password": "Login123"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "Login123"
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert data["role"] == "pengunjung"
 
 
@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "WRONG"
    })
    assert resp.status_code == 401