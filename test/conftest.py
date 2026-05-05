import uuid

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.database import get_db, Base
from app.core.security import create_access_token, hash_password
from app.models.user import User
 
# Gunakan database test terpisah (jangan pakai DB development!)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/smart_tourism_test"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Provide async DB session per test — rollback otomatis setelah tiap test."""
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
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
    async with create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool).begin() as conn:
        session_factory = sessionmaker(bind=conn, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker(create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool), class_=AsyncSession, expire_on_commit=False)() as session:
        existing = await session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": "admin@smarttourism.id"})
        row = existing.fetchone()
        if row:
            user_id = str(row.id)
        else:
            admin = User(
                id=uuid.uuid4(),
                nama="Admin Test",
                email="admin@smarttourism.id",
                password_hash=hash_password("Admin1234"),
                role="admin",
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            user_id = str(admin.id)
    return create_access_token({"sub": user_id, "role": "admin"})
 
 
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
