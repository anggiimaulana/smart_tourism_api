# app/services/nongkrong_service.py
import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.nongkrong import NongkrongCreate, NongkrongUpdate
from app.services.wisata_service import WILAYAH_PREFIX


async def _generate_kode(wilayah: str, db: AsyncSession) -> str:
    wfx    = WILAYAH_PREFIX.get(wilayah, "UNK")
    result = await db.execute(
        text("SELECT COUNT(*) FROM nongkrong WHERE wilayah = :w"), {"w": wilayah}
    )
    count = result.scalar() or 0
    return f"NGK-{wfx}-{(count + 1):03d}"


class NongkrongService:

    async def list(
        self,
        wilayah:  Optional[str],
        sentimen: Optional[str],
        q:        Optional[str],
        sort_by:  Optional[str],
        order:    Optional[str],
        page:     int,
        limit:    int,
        db:       AsyncSession,
    ) -> dict:
        filters: list[str] = ["status = 'aktif'"]
        params:  dict      = {}

        if wilayah:
            filters.append("wilayah = :wilayah");         params["wilayah"] = wilayah
        if sentimen:
            filters.append("sentimen::text = :sentimen"); params["sentimen"] = sentimen
        if q:
            filters.append(
                "(nama ILIKE :q OR konsep_suasana ILIKE :q OR cocok_untuk ILIKE :q)"
            )
            params["q"] = f"%{q}%"

        where  = "WHERE " + " AND ".join(filters)
        offset = (page - 1) * limit

        total_r = await db.execute(text(f"SELECT COUNT(*) FROM nongkrong {where}"), params)
        total   = total_r.scalar() or 0

        # ── Sorting ───────────────────────────────────────────────────────────
        sort_map = {"rating": "rating_google", "sentimen": "skor_sentimen"}
        col = sort_map.get(sort_by, "rating_google")
        ord = "ASC" if order == "asc" else "DESC"
        order_clause = f"ORDER BY {col} {ord} NULLS LAST"

        params["limit"] = limit; params["offset"] = offset
        rows = await db.execute(text(f"""
            SELECT * FROM nongkrong {where}
            {order_clause}
            LIMIT :limit OFFSET :offset
        """), params)

        return {
            "items":       [dict(r._mapping) for r in rows.fetchall()],
            "total":       total,
            "page":        page,
            "limit":       limit,
            "total_pages": math.ceil(total / limit) if total else 0,
        }

    async def get_by_kode(self, kode: str, db: AsyncSession) -> Optional[dict]:
        r = await db.execute(text("SELECT * FROM nongkrong WHERE kode = :k"), {"k": kode})
        row = r.fetchone()
        if not row:
            return None
            
        data = dict(row._mapping)
        if data.get("id_wisata_ref"):
            wis_r = await db.execute(
                text("SELECT * FROM wisata WHERE kode = :k"), 
                {"k": data["id_wisata_ref"]}
            )
            wis_row = wis_r.fetchone()
            data["wisata"] = dict(wis_row._mapping) if wis_row else None
        else:
            data["wisata"] = None
            
        return data

    async def create(self, payload: NongkrongCreate, db: AsyncSession) -> dict:
        kode = await _generate_kode(payload.wilayah.value, db)
        await db.execute(text("""
            INSERT INTO nongkrong (
                kode, id_wisata_ref, nama, wilayah, kecamatan, alamat_lengkap,
                latitude, longitude, konsep_suasana, target_pengunjung,
                cocok_untuk, menu_best_seller, harga_menu_min, harga_menu_max,
                jam_buka, jam_tutup, kapasitas_orang, fasilitas,
                batas_waktu_duduk, rating_google, minimal_order,
                link_google_maps, kontak, gambar, catatan, status
            ) VALUES (
                :kode, :id_ref, :nama, :wilayah, :kecamatan, :alamat,
                :lat, :lon, :konsep, :target,
                :cocok, :menu, :harga_min, :harga_max,
                :jam_buka, :jam_tutup, :kapasitas, :fasilitas,
                :batas, :rating, :min_order,
                :gmaps, :kontak, :gambar, :catatan, :status
            )
        """), {
            "kode":     kode,
            "id_ref":   payload.id_wisata_ref,
            "nama":     payload.nama,
            "wilayah":  payload.wilayah.value,
            "kecamatan": payload.kecamatan,
            "alamat":   payload.alamat_lengkap,
            "lat":      payload.latitude,
            "lon":      payload.longitude,
            "konsep":   payload.konsep_suasana,
            "target":   payload.target_pengunjung,
            "cocok":    payload.cocok_untuk,
            "menu":     payload.menu_best_seller,
            "harga_min": payload.harga_menu_min,
            "harga_max": payload.harga_menu_max,
            "jam_buka": payload.jam_buka,
            "jam_tutup": payload.jam_tutup,
            "kapasitas": payload.kapasitas_orang,
            "fasilitas": payload.fasilitas,
            "batas":    payload.batas_waktu_duduk,
            "rating":   payload.rating_google,
            "min_order": payload.minimal_order,
            "gmaps":    payload.link_google_maps,
            "kontak":   payload.kontak,
            "gambar":   payload.gambar,
            "catatan":  payload.catatan,
            "status":   payload.status.value,
        })
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def update(self, kode: str, payload: NongkrongUpdate, db: AsyncSession) -> Optional[dict]:
        if not await self.get_by_kode(kode, db):
            return None
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if not updates:
            return await self.get_by_kode(kode, db)
        if "status" in updates and hasattr(updates["status"], "value"):
            updates["status"] = updates["status"].value
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["kode"] = kode
        await db.execute(text(f"UPDATE nongkrong SET {set_clause} WHERE kode = :kode"), updates)
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def delete(self, kode: str, db: AsyncSession) -> bool:
        r = await db.execute(
            text("DELETE FROM nongkrong WHERE kode = :kode RETURNING id"), {"kode": kode}
        )
        await db.commit()
        return r.fetchone() is not None