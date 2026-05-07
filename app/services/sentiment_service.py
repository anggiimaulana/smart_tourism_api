"""Sentiment Analysis Service — Anggi (Indramayu + Cirebon).

Fokus pada pengambilan data agregat (summary) dan sinkronisasi data 
dari sentiment_results ke tabel master (wisata, kuliner, nongkrong).
Model AI dikerjakan di Colab, hasil di-seed ke database.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sentiment import (
    SentimentSummaryResponse,
    SentimentSyncResponse,
)

logger = logging.getLogger(__name__)

# ── Slang dict Indramayu + Cirebon ────────────────────────────────────────
SLANG_DICT: Dict[str, str] = {
    "gak": "tidak", "ga": "tidak", "tdk": "tidak", "ngga": "tidak",
    "gk": "tidak", "g": "tidak", "bgs": "bagus", "mantap": "bagus",
    "keren": "bagus", "jelek": "buruk", "ancur": "buruk", "parah": "buruk",
    "enak": "lezat", "yummy": "lezat", "murah": "terjangkau",
    "rame": "ramai", "bs": "bisa", "hrs": "harus", "sdh": "sudah",
    "blm": "belum", "udh": "sudah", "aja": "saja", "yg": "yang",
    "dgn": "dengan", "utk": "untuk", "krn": "karena",
    # Khas Indramayu / Cirebon
    "ewean": "tidak", "ora": "tidak", "sing": "yang",
    "maning": "lagi", "arep": "mau", "apik": "bagus", "ayu": "cantik",
}


def _preprocess(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    t = raw.lower()
    t = re.sub(r"http\S+|www\S+", "", t)
    t = re.sub(r"@\w+|#\w+", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\d+", "", t)
    words = [SLANG_DICT.get(w, w) for w in t.split()]
    words = [w for w in words if w]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


# ── Service ────────────────────────────────────────────────────────────────

class SentimentService:
    """Async service untuk manajemen hasil analisis sentimen."""

    async def get_summary(
        self,
        wilayah: str,
        tipe_tempat: str,
        db: AsyncSession,
    ) -> SentimentSummaryResponse:
        """Agregat sentimen per wilayah dan tipe tempat."""
        type_clause = ""
        params: dict = {"wilayah": wilayah}
        if tipe_tempat != "all":
            type_clause = "AND tempat.tipe_tempat = :tipe_tempat"
            params["tipe_tempat"] = tipe_tempat

        result = await db.execute(text(f"""
            SELECT
                COUNT(*) AS total_ulasan,
                COUNT(*) FILTER (WHERE sr.sentimen = 'positif') AS total_positif,
                COUNT(*) FILTER (WHERE sr.sentimen = 'negatif') AS total_negatif,
                COUNT(*) FILTER (WHERE sr.sentimen = 'netral')  AS total_netral
            FROM sentiment_results sr
            JOIN (
                SELECT kode, wilayah::text AS wilayah, 'wisata'    AS tipe_tempat FROM wisata
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'kuliner'   AS tipe_tempat FROM kuliner
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'nongkrong' AS tipe_tempat FROM nongkrong
            ) tempat ON tempat.kode = sr.tempat_kode
                     AND tempat.tipe_tempat = sr.tipe_tempat::text
            WHERE tempat.wilayah = :wilayah {type_clause}
        """), params)

        row           = result.fetchone()
        total_ulasan  = int(row.total_ulasan  or 0)
        total_positif = int(row.total_positif or 0)
        total_negatif = int(row.total_negatif or 0)
        total_netral  = int(row.total_netral  or 0)

        return SentimentSummaryResponse(
            wilayah=wilayah,
            tipe_tempat=tipe_tempat,
            total_ulasan=total_ulasan,
            total_positif=total_positif,
            total_negatif=total_negatif,
            total_netral=total_netral,
            persen_positif=round(total_positif / total_ulasan * 100, 2) if total_ulasan else 0.0,
            persen_negatif=round(total_negatif / total_ulasan * 100, 2) if total_ulasan else 0.0,
        )

    async def get_summary_all(
        self,
        db: AsyncSession,
    ) -> List[SentimentSummaryResponse]:
        """Ambil summary untuk semua 4 wilayah sekaligus."""
        WILAYAH = ["Indramayu", "Cirebon", "Majalengka", "Kuningan"]
        results = []
        for w in WILAYAH:
            results.append(await self.get_summary(w, "all", db))
        return results

    async def sync_sentimen(
        self,
        tipe_tempat: str,
        kode: str,
        db: AsyncSession,
    ) -> SentimentSyncResponse:
        """Update kolom sentimen di tabel master berdasarkan ulasan di sentiment_results."""
        valid = {"wisata", "kuliner", "nongkrong"}
        if tipe_tempat not in valid:
            raise HTTPException(status_code=400, detail=f"tipe_tempat tidak valid: {tipe_tempat}")

        agg = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE sentimen = 'positif') AS positif,
                COUNT(*) FILTER (WHERE sentimen = 'negatif') AS negatif,
                COUNT(*)                                      AS total
            FROM sentiment_results
            WHERE tempat_kode = :kode AND tipe_tempat = :tipe
        """), {"kode": kode, "tipe": tipe_tempat})

        row     = agg.fetchone()
        total   = int(row.total   or 0)
        positif = int(row.positif or 0)
        negatif = int(row.negatif or 0)

        dominant = "positif" if positif >= negatif else "negatif"
        skor     = round(positif / total, 4) if total else 0.0

        await db.execute(text(f"""
            UPDATE {tipe_tempat}
            SET sentimen             = :sentimen,
                skor_sentimen        = :skor,
                total_ulasan_scraped = :total,
                total_positif        = :positif,
                total_negatif        = :negatif,
                updated_at           = NOW()
            WHERE kode = :kode
        """), {"sentimen": dominant, "skor": skor,
               "total": total, "positif": positif,
               "negatif": negatif, "kode": kode})
        await db.commit()

        return SentimentSyncResponse(
            kode=kode, sentimen=dominant, skor_sentimen=skor,
            total=total, positif=positif, negatif=negatif,
        )

    async def sync_all(self, db: AsyncSession) -> dict:
        """Sinkronisasi semua tempat yang ada di sentiment_results ke tabel master."""
        res = await db.execute(text("SELECT DISTINCT tipe_tempat, tempat_kode FROM sentiment_results"))
        items = res.fetchall()

        count = 0
        for tipe, kode in items:
            # Handle tipe if it's enum
            t_str = tipe.value if hasattr(tipe, 'value') else str(tipe)
            await self.sync_sentimen(t_str, kode, db)
            count += 1
        
        return {"total_synced": count}


__all__ = ["SentimentService"]
