import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIRM_PHRASE = "RESET SMART TOURISM DB"


def build_psql_env() -> dict:
    parsed = urlparse(DATABASE_URL)
    if not parsed.password:
        raise RuntimeError("DATABASE_URL harus berisi password PostgreSQL")

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password
    return env


def run_psql_file(sql_file: str) -> None:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql"}:
        raise RuntimeError("DATABASE_URL tidak valid untuk PostgreSQL")

    command = [
        "psql",
        "-U",
        parsed.username or "postgres",
        "-h",
        parsed.hostname or "localhost",
        "-p",
        str(parsed.port or 5432),
        "-d",
        (parsed.path or "").lstrip("/"),
        "-f",
        str(PROJECT_ROOT / sql_file),
    ]
    subprocess.run(command, check=True, env=build_psql_env())


def run_python_file(script_file: str) -> None:
    subprocess.run([sys.executable, str(PROJECT_ROOT / script_file)], check=True)


async def reset():
    print("\n" + "=" * 50)
    print("  ⚠️  DATABASE RESET TOOL  ⚠️")
    print("=" * 50)
    print("\nPeringatan: semua data akan dihapus permanen!")
    confirm = input(f'\nKetik "{CONFIRM_PHRASE}" untuk melanjutkan: ')

    if confirm.strip() != CONFIRM_PHRASE:
        print("\n[BATAL] Reset dibatalkan.")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Drop semua table dengan CASCADE
        print("\nMenghapus semua tabel...")
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        print("[OK] Semua tabel dihapus.")

    await engine.dispose()

    print("\nMenjalankan schema...")
    run_psql_file("sql/01_schema.sql")

    print("\nMenjalankan FTS...")
    run_psql_file("sql/03_fts.sql")

    print("\nMenjalankan seeding...")
    run_python_file("sql/02_seed.py")

    print("\n[OK] Reset + migrate + seed selesai.")


if __name__ == "__main__":
    asyncio.run(reset())