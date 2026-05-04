import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OUTPUT_DIR   = Path("data/exports")


async def export(wilayah_filter: str | None = None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(DATABASE_URL, echo=False)

    wilayah_cond = ""
    params: dict = {}
    if wilayah_filter:
        wilayah_cond = """
            AND sr.tempat_kode IN (
                SELECT kode FROM wisata   WHERE wilayah = :w
                UNION SELECT kode FROM kuliner  WHERE wilayah = :w
                UNION SELECT kode FROM nongkrong WHERE wilayah = :w
            )
        """
        params["w"] = wilayah_filter

    query = f"""
        SELECT
            sr.id, sr.tipe_tempat, sr.tempat_kode,
            sr.ulasan_asli, sr.ulasan_bersih,
            sr.sentimen, sr.confidence, sr.model_used,
            sr.sumber_scraping, sr.scraped_at, sr.created_at
        FROM sentiment_results sr
        WHERE 1=1 {wilayah_cond}
        ORDER BY sr.created_at DESC
    """

    async with engine.connect() as conn:
        result = await conn.execute(text(query), params)
        rows   = result.fetchall()

    if not rows:
        print(f"[INFO] Tidak ada data sentimen{f' untuk wilayah {wilayah_filter}' if wilayah_filter else ''}.")
        await engine.dispose()
        return

    df       = pd.DataFrame(rows, columns=result.keys())
    suffix   = f"_{wilayah_filter.lower()}" if wilayah_filter else "_all"
    filename = f"sentiment_results{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    outpath  = OUTPUT_DIR / filename

    df.to_excel(outpath, index=False, engine="openpyxl")
    print(f"[OK] Exported {len(df)} baris ke: {outpath}")
    await engine.dispose()


if __name__ == "__main__":
    wilayah = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(export(wilayah))