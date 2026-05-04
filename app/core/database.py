# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,   # cetak SQL ke console hanya saat DEBUG=True
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,    # cek koneksi sebelum dipakai (hindari connection drop)
)

# ── Session Factory ───────────────────────────────────────────
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Base ORM ──────────────────────────────────────────────────
# Diimport oleh semua file di app/models/ sebagai base class
Base = declarative_base()


# ── Dependency ────────────────────────────────────────────────
async def get_db():
    """
    FastAPI dependency — inject AsyncSession ke endpoint.
    Otomatis rollback jika ada exception, otomatis close setelah request selesai.

    Penggunaan di endpoint:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()