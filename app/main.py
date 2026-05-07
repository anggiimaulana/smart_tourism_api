# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine, Base

# Import semua model agar SQLAlchemy tahu tabel mana saja yang perlu dibuat
import app.models  # noqa: F401

from app.api.v1.router import router as api_v1_router

from contextlib import asynccontextmanager

# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Dijalankan saat server start dan stop.
    Untuk development: auto-create tabel jika belum ada.
    """
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield

# ── Inisialisasi App ──────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API Backend Smart Tourism Ciayumajakuning — Cirebon, Indramayu, Majalengka, Kuningan",
    docs_url="/docs"    if settings.DEBUG else None,   # nonaktif di production
    redoc_url="/redoc"  if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global Exception Handler ──────────────────────────────────
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