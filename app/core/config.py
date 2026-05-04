# app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────
    APP_NAME:    str = "Smart Tourism Ciayumajakuning API"
    APP_VERSION: str = "1.0.0"
    DEBUG:       bool = True

    # ── Database ──────────────────────────────────────────────
    # Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
    DATABASE_URL: str

    # ── Gemini ────────────────────────────────────────────────
    # Dapatkan di: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: str

    # ── JWT Auth ──────────────────────────────────────────────
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY:                    str
    ALGORITHM:                     str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:   int = 1440  # 24 jam

    # ── RAG Settings ──────────────────────────────────────────
    RAG_TOP_K:    int   = 5     # jumlah dokumen yang di-retrieve per query
    RAG_MIN_RANK: float = 0.01  # minimum ts_rank agar dokumen lolos

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton — import ini di semua file yang butuh settings
settings = Settings()