# app/services/wisata_service.py
import math
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.wisata import WisataCreate, WisataUpdate

# ── Konstanta shared (diimport oleh kuliner & nongkrong service) ──
WILAYAH_PREFIX = {
    "Indramayu":  "IDM",
    "Cirebon":    "CRB",
    "Majalengka": "MJL",
    "Kuningan":   "KNG",
}


async def _generate_kode(wilayah: str, db: AsyncSession) -> str:
    """
    Generate kode unik berformat WIS-{WILAYAH}-{NOMOR}.
    Contoh: WIS-IDM-042, WIS-CRB-007
    """
    wfx    = WILAYAH_PREFIX.get(wilayah, "UNK")
    result = await db.execute(
        text("SELECT COUNT(*) FROM wisata WHERE wilayah = :w"),
        {"w": wilayah},
    )
    count = result.scalar() or 0
    return f"WIS-{wfx}-{(count + 1):03d}"


class WisataService:
    """
    CRUD Service untuk tabel wisata.
    Semua method adalah async dan menerima AsyncSession dari dependency injection.
    """

    async def list(
        self,
        wilayah:  Optional[str],
        kategori: Optional[str],
        sentimen: Optional[str],
        q:        Optional[str],
        page:     int,
        limit:    int,
        db:       AsyncSession,
    ) -> dict:
        """
        Ambil daftar wisata dengan filter opsional dan pagination.
        Hanya menampilkan status='aktif'.
        """
        filters: list[str] = ["status = 'aktif'"]
        params:  dict      = {}

        if wilayah:
            filters.append("wilayah = :wilayah")
            params["wilayah"] = wilayah
        if kategori:
            filters.append("kategori_utama::text = :kategori")
            params["kategori"] = kategori
        if sentimen:
            filters.append("sentimen::text = :sentimen")
            params["sentimen"] = sentimen
        if q:
            filters.append("(nama ILIKE :q OR deskripsi ILIKE :q OR kecamatan ILIKE :q)")
            params["q"] = f"%{q}%"

        where  = "WHERE " + " AND ".join(filters)
        offset = (page - 1) * limit

        count_r = await db.execute(text(f"SELECT COUNT(*) FROM wisata {where}"), params)
        total   = count_r.scalar() or 0

        params["limit"]  = limit
        params["offset"] = offset
        rows = await db.execute(text(f"""
            SELECT * FROM wisata {where}
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
        """Return satu wisata berdasarkan kode unik, atau None jika tidak ada."""
        row = await db.execute(
            text("SELECT * FROM wisata WHERE kode = :kode"),
            {"kode": kode},
        )
        r = row.fetchone()
        if not r:
            return None
            
        data = dict(r._mapping)
        
        # Ambil kuliner terdekat
        kuliner_rows = await db.execute(
            text("SELECT * FROM kuliner WHERE id_wisata_terdekat = :kode AND status = 'aktif'"),
            {"kode": kode}
        )
        data["kuliner_terdekat"] = [dict(k._mapping) for k in kuliner_rows.fetchall()]
        
        # Ambil nongkrong terkait
        nongkrong_rows = await db.execute(
            text("SELECT * FROM nongkrong WHERE id_wisata_ref = :kode AND status = 'aktif'"),
            {"kode": kode}
        )
        data["tempat_nongkrong"] = [dict(n._mapping) for n in nongkrong_rows.fetchall()]
        
        return data

    async def create(self, payload: WisataCreate, db: AsyncSession) -> dict:
        """
        Insert wisata baru. Kode digenerate otomatis.
        Return dict data wisata yang baru dibuat.
        """
        kode = await _generate_kode(payload.wilayah.value, db)

        await db.execute(text("""
            INSERT INTO wisata (
                uid, kode, nama, wilayah, kecamatan, alamat_lengkap,
                latitude, longitude, kategori_utama, sub_kategori, jenis_tempat,
                deskripsi, harga_tiket_min, harga_tiket_max, gratis,
                jam_buka, jam_tutup, hari_libur_operasional, estimasi_durasi_jam,
                fasilitas, aksesibilitas, moda_transportasi,
                rating_google, jumlah_ulasan_google,
                link_google_maps, link_instagram, link_website, kontak,
                gambar, sumber_data, diinput_oleh, status
            ) VALUES (
                :uid, :kode, :nama, :wilayah, :kecamatan, :alamat,
                :lat, :lon, :kategori, :sub_kategori, :jenis,
                :deskripsi, :harga_min, :harga_max, :gratis,
                :jam_buka, :jam_tutup, :hari_libur, :durasi,
                :fasilitas, :aksesibilitas, :transportasi,
                :rating, :jml_ulasan,
                :gmaps, :ig, :website, :kontak,
                :gambar, :sumber, :diinput, :status
            )
        """), {
            "uid":          str(uuid.uuid4()),
            "kode":         kode,
            "nama":         payload.nama,
            "wilayah":      payload.wilayah.value,
            "kecamatan":    payload.kecamatan,
            "alamat":       payload.alamat_lengkap,
            "lat":          payload.latitude,
            "lon":          payload.longitude,
            "kategori":     payload.kategori_utama,
            "sub_kategori": payload.sub_kategori,
            "jenis":        payload.jenis_tempat,
            "deskripsi":    payload.deskripsi,
            "harga_min":    payload.harga_tiket_min,
            "harga_max":    payload.harga_tiket_max,
            "gratis":       payload.gratis,
            "jam_buka":     payload.jam_buka,
            "jam_tutup":    payload.jam_tutup,
            "hari_libur":   payload.hari_libur_operasional,
            "durasi":       payload.estimasi_durasi_jam,
            "fasilitas":    payload.fasilitas,
            "aksesibilitas": payload.aksesibilitas,
            "transportasi": payload.moda_transportasi,
            "rating":       payload.rating_google,
            "jml_ulasan":   payload.jumlah_ulasan_google,
            "gmaps":        payload.link_google_maps,
            "ig":           payload.link_instagram,
            "website":      payload.link_website,
            "kontak":       payload.kontak,
            "gambar":       payload.gambar,
            "sumber":       payload.sumber_data,
            "diinput":      None,   # diisi sistem, bukan user
            "status":       payload.status.value,
        })
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def update(self, kode: str, payload: WisataUpdate, db: AsyncSession) -> Optional[dict]:
        """
        Update sebagian field (PATCH). Hanya field yang dikirim yang diupdate.
        Return None jika kode tidak ditemukan.
        """
        if not await self.get_by_kode(kode, db):
            return None

        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if not updates:
            return await self.get_by_kode(kode, db)   # tidak ada yang diubah

        # Handle enum value
        if "status" in updates and hasattr(updates["status"], "value"):
            updates["status"] = updates["status"].value

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["kode"] = kode

        await db.execute(
            text(f"UPDATE wisata SET {set_clause} WHERE kode = :kode"),
            updates,
        )
        await db.commit()
        return await self.get_by_kode(kode, db)

    async def delete(self, kode: str, db: AsyncSession) -> bool:
        """
        Hapus wisata berdasarkan kode.
        Return True jika berhasil, False jika tidak ditemukan.
        """
        result = await db.execute(
            text("DELETE FROM wisata WHERE kode = :kode RETURNING id"),
            {"kode": kode},
        )
        await db.commit()
        return result.fetchone() is not None
