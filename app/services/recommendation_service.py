"""Recommendation service template.

Target kerja berdasarkan README:
1. Hasilkan rekomendasi personal, nearby, dan popular secara bertingkat.
2. Gunakan riwayat user untuk collaborative filtering.
3. Gabungkan skor sentimen, rating Google, dan preferensi kategori.
4. Buat itinerary otomatis untuk planning multi-hari.
5. Catat interaksi user sebagai data masukan model rekomendasi.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recommendation import (
	PlanningRequest,
	PlanningResponse,
	RecommendationRequest,
	RecommendationResponse,
	TrackHistoryRequest,
)


class RecommendationService:
	"""Async service placeholder for recommendation and planning workflows."""

	TODO_LIST = [
		"Implement recommendation ranking for personal, nearby, and popular modes.",
		"Combine collaborative filtering with content-based filtering.",
		"Apply sentiment and rating signals from the main data tables.",
		"Implement itinerary generation for multi-day planning.",
		"Store user interactions for future model training.",
	]

	async def recommend(
		self,
		payload: RecommendationRequest,
		db: AsyncSession,
	) -> RecommendationResponse:
		raise NotImplementedError("TODO: implement recommendation ranking pipeline")

	async def create_planning(
		self,
		payload: PlanningRequest,
		db: AsyncSession,
	) -> PlanningResponse:
		raise NotImplementedError("TODO: implement itinerary planning workflow")

	async def track_history(self, payload: TrackHistoryRequest, db: AsyncSession) -> None:
		raise NotImplementedError("TODO: implement recommendation history tracking")


__all__ = ["RecommendationService"]
