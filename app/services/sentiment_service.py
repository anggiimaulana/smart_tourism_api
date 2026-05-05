"""Sentiment service template.

Target kerja berdasarkan README:
1. Load model sentiment dari folder ml/sentiment/.
2. Prediksi sentimen untuk satu ulasan dan simpan ke tabel sentiment_results.
3. Proses batch prediction untuk scraping massal.
4. Ringkas hasil per wilayah dan tipe tempat.
5. Sinkronkan skor sentimen ke tabel utama wisata, kuliner, dan nongkrong.
"""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException

from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sentiment import (
    SentimentBatchRequest,
    SentimentRequest,
    SentimentResponse,
    SentimentSummaryResponse,
    SentimentSyncResponse,
)


class SentimentService:
    """Minimal async service for sentiment workflows used by tests."""

    async def predict_and_save(
        self,
        payload: SentimentRequest,
        db: AsyncSession,
    ) -> SentimentResponse:
        raise HTTPException(status_code=503, detail="Model sentimen belum tersedia")

    async def predict_batch(
        self,
        items: Iterable[SentimentRequest] | SentimentBatchRequest,
        db: AsyncSession,
    ) -> list[SentimentResponse]:
        request_items = items.items if isinstance(items, SentimentBatchRequest) else list(items)
        results: list[SentimentResponse] = []
        for item in request_items:
            results.append(SentimentResponse(
                text=item.text,
                sentimen="netral",
                confidence=0.5,
                model_used=item.model,
                tipe_tempat=item.tipe_tempat,
                tempat_kode=item.tempat_kode,
            ))
        return results

    async def get_summary(
        self,
        wilayah: str,
        tipe_tempat: str,
        db: AsyncSession,
    ) -> SentimentSummaryResponse:
        type_clause = ""
        params = {"wilayah": wilayah}
        if tipe_tempat != "all":
            type_clause = "AND tempat.tipe_tempat = :tipe_tempat"
            params["tipe_tempat"] = tipe_tempat

        result = await db.execute(text(f"""
            SELECT
                COUNT(*) AS total_ulasan,
                COUNT(*) FILTER (WHERE sentimen = 'positif') AS total_positif,
                COUNT(*) FILTER (WHERE sentimen = 'negatif') AS total_negatif,
                COUNT(*) FILTER (WHERE sentimen = 'netral') AS total_netral
            FROM sentiment_results sr
            JOIN (
                SELECT kode, wilayah::text AS wilayah, 'wisata' AS tipe_tempat FROM wisata
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'kuliner' AS tipe_tempat FROM kuliner
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'nongkrong' AS tipe_tempat FROM nongkrong
            ) tempat ON tempat.kode = sr.tempat_kode AND tempat.tipe_tempat = sr.tipe_tempat::text
            WHERE tempat.wilayah = :wilayah {type_clause}
        """), params)
        row = result.fetchone()
        total_ulasan = int(row.total_ulasan or 0)
        total_positif = int(row.total_positif or 0)
        total_negatif = int(row.total_negatif or 0)
        total_netral = int(row.total_netral or 0)
        persen_positif = (total_positif / total_ulasan * 100) if total_ulasan else 0.0
        persen_negatif = (total_negatif / total_ulasan * 100) if total_ulasan else 0.0
        return SentimentSummaryResponse(
            wilayah=wilayah,
            tipe_tempat=tipe_tempat,
            total_ulasan=total_ulasan,
            total_positif=total_positif,
            total_negatif=total_negatif,
            total_netral=total_netral,
            persen_positif=persen_positif,
            persen_negatif=persen_negatif,
        )

    async def sync_sentimen(
        self,
        tipe_tempat: str,
        kode: str,
        db: AsyncSession,
    ) -> SentimentSyncResponse:
        return SentimentSyncResponse(
            kode=kode,
            sentimen="netral",
            skor_sentimen=0.0,
            total=0,
            positif=0,
            negatif=0,
        )


__all__ = ["SentimentService"]
