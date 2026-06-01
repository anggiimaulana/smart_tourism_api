from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────
    APP_NAME:    str = "Smart Tourism Ciayumajakuning API"
    APP_VERSION: str = "1.0.0"
    DEBUG:       bool = True
    LARAVEL_URL: str = "http://127.0.0.1:8000"

    # ── Database ──────────────────────────────────────────────
    # Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
    DATABASE_URL: str

    # ── Gemini ────────────────────────────────────────────────
    # Dapatkan di: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: str = ""

    # ── LLM Provider ─────────────────────────────────────────
    # Pilih: "gemini" atau "groq"
    LLM_PROVIDER: str = "gemini"

    # ── Groq ──────────────────────────────────────────────────
    # Dapatkan di: https://console.groq.com/keys
    GROQ_API_KEY: str = ""
    GROQ_MODEL:   str = "llama-3.3-70b-versatile"

    # ── OpenAI ────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL:   str = "gpt-4o-mini"

    # ── JWT Auth ──────────────────────────────────────────────
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY:                    str
    ALGORITHM:                     str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:   int = 1440  # 24 jam

    # ── RAG Settings ──────────────────────────────────────────
    RAG_TOP_K:    int   = 5     # jumlah dokumen yang di-retrieve per query
    RAG_MIN_SCORE: float = 0.01  # minimum ts_rank agar dokumen lolos

    # ── Cache Settings ────────────────────────────────────────
    CACHE_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Singleton — import ini di semua file yang butuh settings
settings = Settings()