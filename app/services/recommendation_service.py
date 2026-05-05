"""Recommendation service implementation.

Strategi recommendation dibuat berlapis:
1. Personal jika user memiliki histori dan artefak model tersedia.
2. Nearby jika koordinat tersedia.
3. Popular sebagai fallback yang selalu aman.
"""

from __future__ import annotations

import math
import pickle
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recommendation import (
    PlanningDayItem,
    PlanningRequest,
    PlanningResponse,
    RecommendedItem,
    RecommendationRequest,
    RecommendationResponse,
    TrackHistoryRequest,
)

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "recommendation"


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


class RecommendationService:
    """Async recommendation and planning workflows."""

    def __init__(self) -> None:
        self._cf_model = self._load_pickle("cf_model.pkl")
        self._items_df = self._load_pickle("items_df.pkl")

    @staticmethod
    def _load_pickle(file_name: str) -> Any | None:
        file_path = MODEL_DIR / file_name
        if not file_path.exists():
            return None
        try:
            with file_path.open("rb") as file:
                return pickle.load(file)
        except Exception:
            return None

    @staticmethod
    def _build_filters(payload: RecommendationRequest | PlanningRequest) -> tuple[list[str], dict[str, Any]]:
        filters = ["status = 'aktif'"]
        params: dict[str, Any] = {}

        wilayah = getattr(payload, "wilayah", None)
        if wilayah:
            wilayah_values = [item.value if hasattr(item, "value") else str(item) for item in wilayah]
            filters.append("wilayah = ANY(:wilayah)")
            params["wilayah"] = wilayah_values

        kategori = getattr(payload, "kategori", None) or getattr(payload, "preferensi", None)
        if kategori:
            category_clauses = []
            for index, value in enumerate(kategori):
                key = f"kategori_{index}"
                params[key] = f"%{value}%"
                category_clauses.append(
                    f"(COALESCE(kategori_label, '') ILIKE :{key} OR COALESCE(deskripsi, '') ILIKE :{key} OR COALESCE(nama, '') ILIKE :{key})"
                )
            filters.append("(" + " OR ".join(category_clauses) + ")")

        budget_max = getattr(payload, "budget_max", None) or getattr(payload, "budget_total", None)
        jumlah_orang = getattr(payload, "jumlah_orang", 1) or 1
        if budget_max:
            per_orang = max(int(budget_max / jumlah_orang), 0)
            filters.append("COALESCE(harga_min, 0) <= :budget_max")
            params["budget_max"] = per_orang

        tipe = getattr(payload, "tipe", None)
        if tipe and tipe != "all":
            filters.append("tipe = :tipe")
            params["tipe"] = tipe

        return filters, params

    async def _fetch_candidates(
        self,
        payload: RecommendationRequest | PlanningRequest,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        filters, params = self._build_filters(payload)
        where_clause = "WHERE " + " AND ".join(filters)

        query = f"""
            WITH all_tempat AS (
                SELECT
                    id,
                    kode,
                    nama,
                    'wisata' AS tipe,
                    status::text AS status,
                    wilayah::text AS wilayah,
                    kecamatan,
                    alamat_lengkap AS alamat,
                    latitude,
                    longitude,
                    deskripsi,
                    gambar,
                    rating_google,
                    harga_tiket_min AS harga_min,
                    harga_tiket_max AS harga_max,
                    sentimen::text AS sentimen,
                    skor_sentimen,
                    link_google_maps,
                    COALESCE(kategori_utama::text, sub_kategori, jenis_tempat, 'Wisata') AS kategori_label
                FROM wisata
                UNION ALL
                SELECT
                    id,
                    kode,
                    nama,
                    'kuliner' AS tipe,
                    status::text AS status,
                    wilayah::text AS wilayah,
                    kecamatan,
                    alamat_lengkap AS alamat,
                    latitude,
                    longitude,
                    menu_unggulan AS deskripsi,
                    gambar,
                    rating_google,
                    harga_menu_min AS harga_min,
                    harga_menu_max AS harga_max,
                    sentimen::text AS sentimen,
                    skor_sentimen,
                    link_google_maps,
                    COALESCE(kategori_menu_utama, jenis_tempat::text, nama_makanan_khas, 'Kuliner') AS kategori_label
                FROM kuliner
                UNION ALL
                SELECT
                    id,
                    kode,
                    nama,
                    'nongkrong' AS tipe,
                    status::text AS status,
                    wilayah::text AS wilayah,
                    kecamatan,
                    alamat_lengkap AS alamat,
                    latitude,
                    longitude,
                    COALESCE(menu_best_seller, konsep_suasana, cocok_untuk) AS deskripsi,
                    gambar,
                    rating_google,
                    harga_menu_min AS harga_min,
                    harga_menu_max AS harga_max,
                    sentimen::text AS sentimen,
                    skor_sentimen,
                    link_google_maps,
                    COALESCE(konsep_suasana, target_pengunjung, cocok_untuk, 'Nongkrong') AS kategori_label
                FROM nongkrong
            )
            SELECT *
            FROM all_tempat
            {where_clause}
        """

        rows = await db.execute(text(query), params)
        return [dict(row._mapping) for row in rows.fetchall()]

    @staticmethod
    def _to_recommended_item(item: dict[str, Any], score: float) -> RecommendedItem:
        return RecommendedItem(
            id=_to_int(item.get("id")),
            kode=str(item.get("kode") or ""),
            nama=str(item.get("nama") or ""),
            tipe=str(item.get("tipe") or ""),
            wilayah=str(item.get("wilayah") or ""),
            kecamatan=item.get("kecamatan"),
            alamat=item.get("alamat"),
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            deskripsi=item.get("deskripsi"),
            gambar=_to_str_list(item.get("gambar")),
            rating_google=_to_float(item.get("rating_google"), 0.0),
            harga_min=_to_int(item.get("harga_min"), 0),
            harga_max=_to_int(item.get("harga_max"), 0),
            sentimen=item.get("sentimen"),
            skor_sentimen=_to_float(item.get("skor_sentimen"), 0.0),
            link_google_maps=item.get("link_google_maps"),
            skor_rekomendasi=round(score, 4),
        )

    @staticmethod
    def _score_popular(item: dict[str, Any]) -> float:
        rating = _to_float(item.get("rating_google"), 0.0)
        sentiment = _to_float(item.get("skor_sentimen"), 0.0)
        bonus = 0.25 if item.get("sentimen") == "positif" else 0.0
        return (rating * 0.7) + (sentiment * 3.0) + bonus

    async def _get_visited_codes(self, user_id: str, db: AsyncSession) -> set[str]:
        rows = await db.execute(
            text("SELECT tempat_kode FROM user_history WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        return {str(row.tempat_kode) for row in rows.fetchall() if row.tempat_kode}

    async def _popular(self, payload: RecommendationRequest, db: AsyncSession) -> list[RecommendedItem]:
        candidates = await self._fetch_candidates(payload, db)
        ranked = sorted(candidates, key=self._score_popular, reverse=True)
        return [
            self._to_recommended_item(item, self._score_popular(item))
            for item in ranked[: payload.jumlah]
        ]

    async def _nearby(self, payload: RecommendationRequest, db: AsyncSession) -> list[RecommendedItem]:
        if payload.latitude is None or payload.longitude is None:
            return []

        candidates = await self._fetch_candidates(payload, db)
        scored: list[tuple[dict[str, Any], float]] = []
        for item in candidates:
            lat = item.get("latitude")
            lon = item.get("longitude")
            if lat is None or lon is None:
                continue
            distance = _haversine(payload.latitude, payload.longitude, float(lat), float(lon))
            proximity_score = max(0.0, 100.0 - distance)
            score = proximity_score + self._score_popular(item)
            scored.append((item, score))

        scored.sort(key=lambda row: row[1], reverse=True)
        return [self._to_recommended_item(item, score) for item, score in scored[: payload.jumlah]]

    async def _personal(self, payload: RecommendationRequest, db: AsyncSession) -> list[RecommendedItem]:
        if not payload.user_id:
            return []

        visited_codes = await self._get_visited_codes(payload.user_id, db)
        if not visited_codes:
            return []

        candidates = await self._fetch_candidates(payload, db)
        filtered = [item for item in candidates if item.get("kode") not in visited_codes]
        if not filtered:
            return []

        ranked: list[tuple[dict[str, Any], float]] = []
        for item in filtered:
            score = self._score_popular(item)
            if self._cf_model is not None:
                try:
                    prediction = self._cf_model.predict(str(payload.user_id), str(item.get("kode")))
                    score += _to_float(getattr(prediction, "est", None), 0.0)
                except Exception:
                    pass
            ranked.append((item, score))

        ranked.sort(key=lambda row: row[1], reverse=True)
        return [self._to_recommended_item(item, score) for item, score in ranked[: payload.jumlah]]

    async def recommend(
        self,
        payload: RecommendationRequest,
        db: AsyncSession,
    ) -> RecommendationResponse:
        if payload.mode == "nearby":
            items = await self._nearby(payload, db)
            if items:
                return RecommendationResponse(mode="nearby", total=len(items), items=items)

        if payload.mode == "personal":
            items = await self._personal(payload, db)
            if items:
                return RecommendationResponse(mode="personal", total=len(items), items=items)
            if payload.latitude is not None and payload.longitude is not None:
                items = await self._nearby(payload, db)
                if items:
                    return RecommendationResponse(mode="nearby", total=len(items), items=items)

        items = await self._popular(payload, db)
        return RecommendationResponse(mode="popular", total=len(items), items=items)

    async def create_planning(
        self,
        payload: PlanningRequest,
        db: AsyncSession,
    ) -> PlanningResponse:
        base_request = RecommendationRequest(
            user_id=payload.user_id,
            wilayah=payload.wilayah,
            kategori=payload.preferensi,
            budget_max=payload.budget_total,
            tipe="all",
            jumlah=max(payload.jumlah_hari * 3, payload.jumlah_hari * 2),
            mode="personal" if payload.user_id else "popular",
        )
        recommendation = await self.recommend(base_request, db)
        source_items = recommendation.items

        per_day = max(2, math.ceil(len(source_items) / payload.jumlah_hari)) if source_items else 0
        days: list[PlanningDayItem] = []
        start_date = None
        if payload.tanggal_mulai:
            try:
                start_date = datetime.strptime(payload.tanggal_mulai, "%Y-%m-%d").date()
            except ValueError:
                start_date = None

        for index in range(payload.jumlah_hari):
            start = index * per_day
            end = start + per_day
            day_items = source_items[start:end]
            if not day_items and source_items:
                day_items = source_items[-min(2, len(source_items)):]

            tanggal = None
            if start_date is not None:
                tanggal = (start_date + timedelta(days=index)).isoformat()

            days.append(PlanningDayItem(hari=index + 1, tanggal=tanggal, items=day_items))

        if payload.user_id:
            tanggal_mulai = start_date
            tanggal_selesai = start_date + timedelta(days=payload.jumlah_hari - 1) if start_date else None
            await db.execute(
                text("""
                    INSERT INTO planning_wisata (
                        user_id, judul, wilayah, tanggal_mulai, tanggal_selesai,
                        jumlah_orang, budget_total, catatan, items, status
                    ) VALUES (
                        :user_id, :judul, :wilayah, :tanggal_mulai, :tanggal_selesai,
                        :jumlah_orang, :budget_total, :catatan, CAST(:items AS jsonb), 'draft'
                    )
                """),
                {
                    "user_id": payload.user_id,
                    "judul": f"Planning {', '.join([w.value if hasattr(w, 'value') else str(w) for w in payload.wilayah])}",
                    "wilayah": [w.value if hasattr(w, 'value') else str(w) for w in payload.wilayah],
                    "tanggal_mulai": tanggal_mulai,
                    "tanggal_selesai": tanggal_selesai,
                    "jumlah_orang": payload.jumlah_orang,
                    "budget_total": payload.budget_total,
                    "catatan": payload.catatan_tambahan,
                    "items": PlanningResponse(
                        judul="tmp",
                        wilayah=[],
                        jumlah_hari=payload.jumlah_hari,
                        estimasi_budget=payload.budget_total,
                        hari=days,
                    ).model_dump_json(),
                },
            )
            await db.commit()

        return PlanningResponse(
            judul=f"Itinerary {payload.jumlah_hari} Hari",
            wilayah=[w.value if hasattr(w, "value") else str(w) for w in payload.wilayah],
            jumlah_hari=payload.jumlah_hari,
            estimasi_budget=payload.budget_total,
            hari=days,
        )

    async def track_history(self, payload: TrackHistoryRequest, db: AsyncSession) -> None:
        row = await db.execute(
            text(f"SELECT id FROM {payload.tipe_tempat} WHERE kode = :kode"),
            {"kode": payload.tempat_kode},
        )
        place = row.fetchone()
        if not place:
            raise ValueError("Tempat tidak ditemukan")

        await db.execute(
            text("""
                INSERT INTO user_history (
                    user_id, tipe_tempat, tempat_id, tempat_kode, aksi, nilai_rating, durasi_detik
                ) VALUES (
                    :user_id, :tipe_tempat, :tempat_id, :tempat_kode, :aksi, :nilai_rating, :durasi_detik
                )
            """),
            {
                "user_id": payload.user_id,
                "tipe_tempat": payload.tipe_tempat,
                "tempat_id": place.id,
                "tempat_kode": payload.tempat_kode,
                "aksi": payload.aksi,
                "nilai_rating": payload.nilai_rating,
                "durasi_detik": payload.durasi_detik,
            },
        )
        await db.commit()


__all__ = ["RecommendationService"]
