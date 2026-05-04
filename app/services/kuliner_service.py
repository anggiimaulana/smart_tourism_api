# app/services/kuliner_service.py
# Pola identik dengan wisata_service.py — hanya beda nama tabel & kolom
import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.kuliner import KulinerCreate, KulinerUpdate
from app.services.wisata_service import WILAYAH_PREFIX


async def _generate_kode(wilayah: str, db: AsyncSession) -> str:
    wfx    = WILAYAH_PREFIX.get(wilayah, "UNK")
    result = await db.execute(
        text("SELECT COUNT(*) FROM kuliner WHERE wilayah = :w"), {"w": wilayah}
    )
    count = result.scalar() or 0
    return f"KUL-{wfx}-{(count + 1):03d}"


class KulinerService:

    async def list(
        self,
        wilayah:  Optional[str],
        jenis:    Optional[str],
        sentimen: Optional[str],
        halal:    Optional[bool],
        q:        Optional[str],
        page:     int,
        limit:    int,
        db:       AsyncSession,
    ) -> dict:
        filters: list[str] = ["status = 'aktif'"]
        params:  dict      = {}

        if wilayah:
            filters.append("wilayah = :wilayah");              params["wilayah"] = wilayah
        if jenis:
            filters.append("jenis_tempat::text = :jenis");     params["jenis"] = jenis
        if sentimen:
            filters.append("sentimen::text = :sentimen");      params["sentimen"] = sentimen
        if halal is not None:
            filters.append("sertifikat_halal = :halal");       params["halal"] = halal
        if q:
            filters.append("(nama ILIKE :q OR menu_unggulan ILIKE :q OR nama_makanan_khas ILIKE :q)")
            params["q"] = f"%{q}%"

        where  = "WHERE " + " AND ".join(filters)
        offset = (page - 1) * limit

        total_r = await db.execute(text(f"SELECT COUNT(*) FROM kuliner {where}"), params)
        total   = total_r.scalar() or 0

        params["limit"] = limit; params["offset"] = offset
        rows = await db.execute(text(f"""
            SELECT * FROM kuliner {where}
            ORDER BY rating_google DESC NULLS LAST, skor_sentimen DESC NULLS LAST
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
        r = await db.execute(text("SELECT * FROM kuliner WHERE kode = :k"), {"k": kode})
        row = r.fetchone()
        if not row:
            return None
            
        data = dict(row._mapping)
        if data.get("id_wisata_terdekat"):
            wis_r = await db.execute(
                text("SELECT * FROM wisata WHERE kode = :k"), 
                {"k": data["id_wisata_terdekat"]}
            )
            wis_row = wis_r.fetchone()
            data["wisata"] = dict(wis_row._mapping) if wis_row else None
        else:
            data["wisata"] = None
            
        return data

    async def create(self, payload: KulinerCreate, db: AsyncSession) -> dict:
        kode = await _generate_kode(payload.wilayah.value, db)
        await db.execute(text("""
            INSERT INTO kuliner (
                kode, id_wisata_terdekat, nama, wilayah, kecamatan, alamat_lengkap,
                latitude, longitude, jenis_tempat, kategori_menu_utama, menu_unggulan,
                makanan_khas_daerah, nama_makanan_khas, harga_menu_min, harga_menu_max,
                jam_buka, jam_tutup, kapasitas_orang, fasilitas, sertifikat_halal,
                rating_google, jumlah_ulasan_google, link_google_maps, kontak,
                gambar, catatan, status
            ) VALUES (
                :kode, :id_wisata, :nama, :wilayah, :kecamatan, :alamat,
                :lat, :lon, :jenis, :kategori, :menu,
                :mkd, :nama_mkd, :harga_min, :harga_max,
                :jam_buka, :jam_tutup, :kapasitas, :fasilitas, :halal,
                :rating, :jml_ulasan, :gmaps, :kontak,
                :gambar, :catatan, :status
            )
        """), {
            "kode":       kode,
            "id_wisata":  payload.id_wisata_terdekat,
            "nama":       payload.nama,
            "wilayah":    payload.wilayah.value,
            "kecamatan":  payload.kecamatan,
            "alamat":     payload.alamat_lengkap,
            "lat":        payload.latitude,
            "lon":        payload.longitude,
            "jenis":      payload.jenis_tempat,
            "kategori":   payload.kategori_menu_utama,
            "menu":       payload.menu_unggulan,
            "mkd":        payload.makanan_khas_daerah,
            "nama_mkd":   payload.nama_makanan_khas,
            "harga_min":  payload.harga_menu_min,
            "harga_max":  payload.harga_menu_max,
            "jam_buka":   payload.jam_buka,
            "jam_tutup":  payload.jam_tutup,
            "kapasitas":  payload.kapasitas_orang,
            "fasilitas":  payload.fasilitas,
            "halal":      payload.sertifikat_halal,
            "rating":     payload.rating_google,
            "jml_ulasan": payload.jumlah_ulasan_google,
            "gmaps":      payload.link_google_maps,
            "kontak":     payload.kontak,
            "gambar":     payload.gambar,
            "catatan":    payload.catatan,
            "status":     payload.status.value,
        })
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def update(self, kode: str, payload: KulinerUpdate, db: AsyncSession) -> Optional[dict]:
        if not await self.get_by_kode(kode, db):
            return None
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if not updates:
            return await self.get_by_kode(kode, db)
        if "status" in updates and hasattr(updates["status"], "value"):
            updates["status"] = updates["status"].value
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["kode"] = kode
        await db.execute(text(f"UPDATE kuliner SET {set_clause} WHERE kode = :kode"), updates)
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def delete(self, kode: str, db: AsyncSession) -> bool:
        r = await db.execute(
            text("DELETE FROM kuliner WHERE kode = :kode RETURNING id"), {"kode": kode}
        )
        await db.commit()
        return r.fetchone() is not None