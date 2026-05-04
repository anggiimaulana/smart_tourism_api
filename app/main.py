# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine, Base

# Import semua model agar SQLAlchemy tahu tabel mana saja yang perlu dibuat
import app.models  # noqa: F401

from app.api.v1.router import router as api_v1_router

# ── Inisialisasi App ──────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API Backend Smart Tourism Ciayumajakuning — Cirebon, Indramayu, Majalengka, Kuningan",
    docs_url="/docs"    if settings.DEBUG else None,   # nonaktif di production
    redoc_url="/redoc"  if settings.DEBUG else None,
)

# ── CORS ──────────────────────────────────────────────────────
# Tambahkan origin frontend (Next.js) dan middleware (Laravel) di sini
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js (Sprint 3)
        "http://localhost:8000",   # Laravel middleware (Sprint 3)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global Exception Handler ──────────────────────────────────
# Semua unhandled exception akan menghasilkan response JSON konsisten
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": str(exc) if settings.DEBUG else "Internal server error",
            "data": None,
        },
    )

# ── Startup Event ─────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """
    Dijalankan satu kali saat server pertama kali start.
    Untuk development: auto-create tabel jika belum ada.
    Untuk production: gunakan Alembic migration, jangan auto-create.
    """
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

# ── Health Check ──────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "app":    settings.APP_NAME,
        "version": settings.APP_VERSION,
    }

# ── Router ────────────────────────────────────────────────────
app.include_router(api_v1_router, prefix="/api/v1")