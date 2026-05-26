# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine, Base
from app.services.chatbot_service import get_llm_runtime_status

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
    import logging
    logger = logging.getLogger(__name__)
    llm_status = get_llm_runtime_status()
    logger.info(
        "LLM startup status: gemini=%s groq=%s enabled=%s provider=%s",
        llm_status["gemini_enabled"],
        llm_status["groq_enabled"],
        llm_status["llm_enabled"],
        llm_status["provider"],
    )
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

# ── Global Exception Handlers ─────────────────────────────────
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle semua HTTP errors (401, 403, 404, 405, dll) dengan format konsisten."""
    messages = {
        400: "Permintaan tidak valid. Periksa kembali data yang dikirim.",
        401: "Autentikasi diperlukan. Silakan login terlebih dahulu.",
        403: "Akses ditolak. Anda tidak memiliki izin untuk mengakses resource ini.",
        404: "Resource tidak ditemukan. Periksa kembali URL atau ID yang diminta.",
        405: "Method HTTP tidak diizinkan untuk endpoint ini.",
        409: "Konflik data. Resource sudah ada atau sedang digunakan.",
        429: "Terlalu banyak permintaan. Silakan coba beberapa saat lagi.",
    }
    message = messages.get(exc.status_code, exc.detail or "Terjadi kesalahan.")
    # Jika exc.detail berisi pesan custom dari raise HTTPException, gunakan itu
    if exc.detail and exc.detail != "Not Found":
        message = exc.detail

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": message,
            "data": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle 422 Validation Error — format yang mudah dimengerti."""
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error.get("loc", []) if loc != "body")
        msg = error.get("msg", "")
        errors.append(f"{field}: {msg}" if field else msg)

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Data yang dikirim tidak valid. Periksa kembali format request.",
            "errors": errors,
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle 500 Internal Server Error — jangan expose detail di production."""
    error_msg = (
        f"Terjadi kesalahan internal: {type(exc).__name__}"
        if settings.DEBUG
        else "Terjadi kesalahan pada server. Silakan coba beberapa saat lagi."
    )
    # Log error untuk debugging
    import traceback
    print(f"[ERROR 500] {request.method} {request.url}")
    print(f"  {type(exc).__name__}: {exc}")
    if settings.DEBUG:
        traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": error_msg,
            "data": None,
            "traceback": traceback.format_exc() if settings.DEBUG else None
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