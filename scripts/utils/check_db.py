import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TABLES = [
    "users", "wisata", "kuliner", "nongkrong",
    "sentiment_results", "user_history", "user_preferences",
    "chatbot_sessions", "planning_wisata",
]


async def check():
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL tidak ditemukan di .env")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    print("\n" + "=" * 50)
    print("  Smart Tourism — DB Health Check")
    print("=" * 50)

    try:
        async with engine.connect() as conn:
            print("\n[OK] Koneksi database berhasil\n")
            print(f"{'Tabel':<30} {'Jumlah Row':>12}")
            print("-" * 44)
            for table in TABLES:
                try:
                    result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count  = result.scalar()
                    status = "⚠  KOSONG" if count == 0 else ""
                    print(f"{table:<30} {count:>12}  {status}")
                except Exception as e:
                    print(f"{table:<30} {'ERROR':>12}  ← {e}")
            print("\n[OK] Check selesai.")
    except Exception as e:
        print(f"\n[ERROR] Tidak bisa konek ke database: {e}")
        print("Pastikan PostgreSQL berjalan dan DATABASE_URL sudah benar di .env")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())