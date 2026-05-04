import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
 
from app.main import app
from app.core.database import get_db, Base
 
# Gunakan database test terpisah (jangan pakai DB development!)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/smart_tourism_test"
 
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession  = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
 
 
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
 
 
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Buat semua tabel sebelum test dimulai, drop setelah selesai."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
 
 
@pytest_asyncio.fixture
async def db_session():
    """Provide async DB session per test — rollback otomatis setelah tiap test."""
    async with TestSession() as session:
        yield session
        await session.rollback()
 
 
@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """HTTP test client dengan DB session yang sudah di-override."""
    async def override_get_db():
        yield db_session
 
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
 
 
@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    """Token JWT admin untuk test endpoint yang butuh auth admin."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@smarttourism.id",
        "password": "Admin1234"
    })
    return resp.json()["data"]["access_token"]
 
 
@pytest_asyncio.fixture
async def user_token(client: AsyncClient) -> str:
    """Token JWT user biasa."""
    await client.post("/api/v1/auth/register", json={
        "nama": "Test User",
        "email": "test@user.com",
        "password": "Test1234"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@user.com",
        "password": "Test1234"
    })
    return resp.json()["data"]["access_token"]