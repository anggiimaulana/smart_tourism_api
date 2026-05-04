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

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sentiment import (
	SentimentBatchRequest,
	SentimentRequest,
	SentimentResponse,
	SentimentSummaryResponse,
	SentimentSyncResponse,
)


class SentimentService:
	"""Async service placeholder for sentiment workflows."""

	TODO_LIST = [
		"Load model artifacts from ml/sentiment/ before inference.",
		"Implement single-text prediction and persist sentiment_results.",
		"Implement batch prediction with the 100-item limit from the schema.",
		"Implement summary aggregation by wilayah and tipe_tempat.",
		"Implement sync logic to update sentimen and skor_sentimen on target tables.",
	]

	async def predict_and_save(
		self,
		payload: SentimentRequest,
		db: AsyncSession,
	) -> SentimentResponse:
		raise NotImplementedError("TODO: implement single sentiment prediction and persistence")

	async def predict_batch(
		self,
		items: Iterable[SentimentRequest] | SentimentBatchRequest,
		db: AsyncSession,
	) -> list[SentimentResponse]:
		raise NotImplementedError("TODO: implement batch sentiment prediction workflow")

	async def get_summary(
		self,
		wilayah: str,
		tipe_tempat: str,
		db: AsyncSession,
	) -> SentimentSummaryResponse:
		raise NotImplementedError("TODO: implement sentiment summary aggregation")

	async def sync_sentimen(
		self,
		tipe_tempat: str,
		kode: str,
		db: AsyncSession,
	) -> SentimentSyncResponse:
		raise NotImplementedError("TODO: implement sentiment sync to main tables")


__all__ = ["SentimentService"]
