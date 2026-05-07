"""
02_seed.py — Smart Tourism Ciayumajakuning
Seed data dari Excel ke PostgreSQL. Aman dijalankan berulang (idempotent).

Penggunaan:
    python 02_seed.py

Pastikan .env sudah ada dan PostgreSQL sudah jalan.
"""

import asyncio
import os
import re
import sys
from uuid import uuid4
from datetime import datetime, time
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

# ── Konfigurasi ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+asyncpg://...

# Path file Excel — sesuaikan jika berbeda
WISATA_FILE    = Path("data/Wisata.xlsx")
KULINER_FILE   = Path("data/Kuliner.xlsx")
NONGKRONG_FILE = Path("data/Nongkrong.xlsx")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Helper Functions ───────────────────────────────────────────────────────────

def safe_str(val, default=None) -> str | None:
    """Konversi nilai ke string, return default jika NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return str(val).strip() or default


def safe_int(val, default=0) -> int:
    """Konversi ke int, return default jika tidak valid."""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def safe_float(val, default=None) -> float | None:
    """Konversi ke float, return default jika tidak valid."""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_bool(val, true_values=("ya", "true", "1", "yes")) -> bool:
    """Konversi string 'Ya'/'Tidak' ke boolean."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    return str(val).strip().lower() in true_values


def parse_time(val) -> str | None:
    """Parse berbagai format waktu ke datetime.time."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    s = str(val).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})", s)
    if match:
        return time(hour=int(match.group(1)), minute=int(match.group(2)), second=0)
    return None


def parse_fasilitas(val) -> list[str]:
    """Konversi string fasilitas CSV ke list."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return []
    return [f.strip() for f in str(val).split(",") if f.strip()]


def normalize_wilayah(val) -> str | None:
    """Normalisasi nama wilayah ke enum yang valid."""
    MAP = {
        "indramayu": "Indramayu",
        "cirebon": "Cirebon",
        "majalengka": "Majalengka",
        "kuningan": "Kuningan",
    }
    if not val:
        return None
    return MAP.get(str(val).strip().lower(), str(val).strip())


def normalize_kategori(val) -> str | None:
    """Normalisasi kategori wisata ke enum yang valid."""
    VALID = {"Alam", "Buatan", "Budaya", "Religi", "Petualangan", "Edukasi", "Lainnya"}
    if not val:
        return "Lainnya"
    v = str(val).strip()
    return v if v in VALID else "Lainnya"


def normalize_jenis_kuliner(val) -> str:
    VALID = {"Restoran", "Warung", "Cafe", "Kedai", "Food Court", "Angkringan", "Lainnya"}
    if not val:
        return "Lainnya"
    v = str(val).strip()
    return v if v in VALID else "Lainnya"


def normalize_wisata_ref(val, sheet_name: str | None = None) -> str | None:
    """Normalisasi referensi wisata ke format kode WIS-XXX-000."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None

    ref = str(val).strip()
    if not ref or ref in {"-", "None", "nan"}:
        return None

    if ref.startswith("WIS-"):
        return ref

    match = re.match(r"^(IDM|CRB|MJK|KNG)-(\d{3})$", ref, re.IGNORECASE)
    if match:
        return f"WIS-{match.group(1).upper()}-{match.group(2)}"

    if sheet_name:
        sheet_map = {
            "indramayu": "IDM",
            "cirebon": "CRB",
            "majalengka": "MJK",
            "kuningan": "KNG",
        }
        prefix = sheet_map.get(str(sheet_name).strip().lower())
        if prefix and re.match(r"^\d{3}$", ref):
            return f"WIS-{prefix}-{ref}"

    return ref


def iter_excel_sheets(path: Path):
    workbook = pd.read_excel(path, sheet_name=None)
    for sheet_name, df in workbook.items():
        if df is None or df.empty:
            continue
        yield sheet_name, df

# ── Seed Wisata ────────────────────────────────────────────────────────────────

async def seed_wisata(session: AsyncSession) -> int:
    inserted = 0
    skipped = 0

    for sheet_name, df in iter_excel_sheets(WISATA_FILE):
        sheet_wilayah = normalize_wilayah(sheet_name)

        for _, row in df.iterrows():
            kode = safe_str(row.get("ID_Wisata"))
            if not kode:
                continue

            # Cek duplikat
            exists = await session.execute(
                text("SELECT 1 FROM wisata WHERE kode = :kode"), {"kode": kode}
            )
            if exists.fetchone():
                skipped += 1
                continue

            fasilitas = parse_fasilitas(row.get("Fasilitas"))
            wilayah   = sheet_wilayah or normalize_wilayah(row.get("Wilayah"))
            kategori  = normalize_kategori(row.get("Kategori_Utama"))

            await session.execute(text("""
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
                    :lat, :lon, :kategori, :sub_kategori, :jenis_tempat,
                    :deskripsi, :harga_min, :harga_max, :gratis,
                    :jam_buka, :jam_tutup, :hari_libur, :durasi,
                    :fasilitas, :aksesibilitas, :transportasi,
                    :rating, :jumlah_ulasan,
                    :gmaps, :instagram, :website, :kontak,
                    :gambar, :sumber, :diinput, :status
                )
            """), {
                    "uid":          uuid4(),
                    "kode":         kode,
                    "nama":         safe_str(row.get("Nama_Wisata"), ""),
                    "wilayah":      wilayah,
                    "kecamatan":    safe_str(row.get("Kecamatan")),
                    "alamat":       safe_str(row.get("Alamat_Lengkap")),
                    "lat":          safe_float(row.get("Latitude")),
                    "lon":          safe_float(row.get("Longitude")),
                    "kategori":     kategori,
                    "sub_kategori": safe_str(row.get("Sub_Kategori")),
                    "jenis_tempat": safe_str(row.get("Jenis_Tempat")),
                    "deskripsi":    safe_str(row.get("Deskripsi_Singkat")),
                    "harga_min":    safe_int(row.get("Harga_Tiket_Min")),
                    "harga_max":    safe_int(row.get("Harga_Tiket_Max")),
                    "gratis":       safe_bool(row.get("Gratis")),
                    "jam_buka":     parse_time(row.get("Jam_Buka")),
                    "jam_tutup":    parse_time(row.get("Jam_Tutup")),
                    "hari_libur":   safe_str(row.get("Hari_Libur_Operasional")),
                    "durasi":       safe_float(row.get("Estimasi_Durasi_Jam")),
                    "fasilitas":    fasilitas,
                    "aksesibilitas": safe_str(row.get("Aksesibilitas")),
                    "transportasi": safe_str(row.get("Moda_Transportasi")),
                    "rating":       safe_float(row.get("Rating_Google")),
                    "jumlah_ulasan": safe_int(row.get("Jumlah_Ulasan_Google")),
                    "gmaps":        safe_str(row.get("Link_Google_Maps")),
                    "instagram":    safe_str(row.get("Link_Instagram")),
                    "website":      safe_str(row.get("Link_Website_Resmi")),
                    "kontak":       safe_str(row.get("Kontak_HP")),
                    "gambar":       [],
                    "sumber":       safe_str(row.get("Sumber_Data")),
                    "diinput":      safe_str(row.get("Diinput_Oleh")),
                    "status":       "aktif",
                })
            inserted += 1

    await session.commit()
    return inserted, skipped

# ── Seed Kuliner ───────────────────────────────────────────────────────────────

async def seed_kuliner(session: AsyncSession) -> tuple[int, int]:
    inserted = 0
    skipped = 0

    for sheet_name, df in iter_excel_sheets(KULINER_FILE):
        sheet_wilayah = normalize_wilayah(sheet_name)

        for _, row in df.iterrows():
            kode = safe_str(row.get("ID_Kuliner"))
            if not kode:
                continue

            exists = await session.execute(
                text("SELECT 1 FROM kuliner WHERE kode = :kode"), {"kode": kode}
            )
            if exists.fetchone():
                skipped += 1
                continue

            fasilitas        = parse_fasilitas(row.get("Fasilitas"))
            id_wisata_dekat  = normalize_wisata_ref(row.get("ID_Wisata_Terdekat"), sheet_name)
            wilayah          = sheet_wilayah or normalize_wilayah(row.get("Wilayah"))
            jenis            = normalize_jenis_kuliner(row.get("Jenis_Tempat"))

            # Validasi FK wisata (set NULL jika tidak ada)
            if id_wisata_dekat:
                fk_check = await session.execute(
                    text("SELECT 1 FROM wisata WHERE kode = :kode"), {"kode": id_wisata_dekat}
                )
                if not fk_check.fetchone():
                    id_wisata_dekat = None

            await session.execute(text("""
                INSERT INTO kuliner (
                    uid, kode, id_wisata_terdekat, nama, wilayah, kecamatan, alamat_lengkap,
                    latitude, longitude, jenis_tempat, kategori_menu_utama,
                    menu_unggulan, makanan_khas_daerah, nama_makanan_khas,
                    harga_menu_min, harga_menu_max, jam_buka, jam_tutup,
                    kapasitas_orang, fasilitas, sertifikat_halal,
                    rating_google, jumlah_ulasan_google,
                    link_google_maps, kontak, gambar, sumber_data, status
                ) VALUES (
                    :uid, :kode, :id_wisata, :nama, :wilayah, :kecamatan, :alamat,
                    :lat, :lon, :jenis, :kategori_menu,
                    :menu, :mkd, :nama_mkd,
                    :harga_min, :harga_max, :jam_buka, :jam_tutup,
                    :kapasitas, :fasilitas, :halal,
                    :rating, :ulasan,
                    :gmaps, :kontak, :gambar, :sumber, :status
                )
            """), {
                    "uid":          uuid4(),
                    "kode":         kode,
                    "id_wisata":    id_wisata_dekat,
                    "nama":         safe_str(row.get("Nama_Tempat"), ""),
                    "wilayah":      wilayah,
                    "kecamatan":    safe_str(row.get("Kecamatan")),
                    "alamat":       safe_str(row.get("Alamat_Lengkap")),
                    "lat":          safe_float(row.get("Latitude")),
                    "lon":          safe_float(row.get("Longitude")),
                    "jenis":        jenis,
                    "kategori_menu": safe_str(row.get("Kategori_Menu_Utama")),
                    "menu":         safe_str(row.get("Menu_Unggulan")),
                    "mkd":          safe_bool(row.get("Makanan_Khas_Daerah")),
                    "nama_mkd":     safe_str(row.get("Nama_Makanan_Khas")),
                    "harga_min":    safe_int(row.get("Harga_Menu_Min")),
                    "harga_max":    safe_int(row.get("Harga_Menu_Max")),
                    "jam_buka":     parse_time(row.get("Jam_Buka")),
                    "jam_tutup":    parse_time(row.get("Jam_Tutup")),
                    "kapasitas":    safe_int(row.get("Kapasitas_Orang")),
                    "fasilitas":    fasilitas,
                    "halal":        safe_bool(row.get("Sertifikat_Halal")),
                    "rating":       safe_float(row.get("Rating_Google")),
                    "ulasan":       safe_int(row.get("Jumlah_Ulasan_Google")),
                    "gmaps":        safe_str(row.get("Link_Google_Maps")),
                    "kontak":       safe_str(row.get("Kontak")),
                    "gambar":       [],
                    "sumber":       safe_str(row.get("Sumber_Data")),
                    "status":       "aktif",
                })
            inserted += 1

    await session.commit()
    return inserted, skipped

# ── Seed Nongkrong ─────────────────────────────────────────────────────────────

async def seed_nongkrong(session: AsyncSession) -> tuple[int, int]:
    inserted = 0
    skipped = 0

    for sheet_name, df in iter_excel_sheets(NONGKRONG_FILE):
        sheet_wilayah = normalize_wilayah(sheet_name)

        for _, row in df.iterrows():
            kode = safe_str(row.get("ID_Nongkrong"))
            if not kode:
                continue

            exists = await session.execute(
                text("SELECT 1 FROM nongkrong WHERE kode = :kode"), {"kode": kode}
            )
            if exists.fetchone():
                skipped += 1
                continue

            fasilitas = parse_fasilitas(row.get("Fasilitas"))
            wilayah   = sheet_wilayah or normalize_wilayah(row.get("Wilayah"))
            id_wisata_ref = normalize_wisata_ref(row.get("ID_Wisata_Ref"), sheet_name)

            if id_wisata_ref:
                fk_check = await session.execute(
                    text("SELECT 1 FROM wisata WHERE kode = :kode"), {"kode": id_wisata_ref}
                )
                if not fk_check.fetchone():
                    id_wisata_ref = None

            await session.execute(text("""
                INSERT INTO nongkrong (
                    uid, kode, id_wisata_ref, nama, wilayah, kecamatan, alamat_lengkap,
                    latitude, longitude, konsep_suasana, target_pengunjung,
                    cocok_untuk, menu_best_seller,
                    harga_menu_min, harga_menu_max, jam_buka, jam_tutup,
                    kapasitas_orang, fasilitas, batas_waktu_duduk,
                    rating_google, minimal_order,
                    link_google_maps, kontak, gambar, sumber_data, status
                ) VALUES (
                    :uid, :kode, :id_ref, :nama, :wilayah, :kecamatan, :alamat,
                    :lat, :lon, :konsep, :target,
                    :cocok, :menu_bs,
                    :harga_min, :harga_max, :jam_buka, :jam_tutup,
                    :kapasitas, :fasilitas, :batas_duduk,
                    :rating, :min_order,
                    :gmaps, :kontak, :gambar, :sumber, :status
                )
            """), {
                    "uid":       uuid4(),
                    "kode":      kode,
                    "id_ref":    id_wisata_ref,
                    "nama":      safe_str(row.get("Nama_Tempat"), ""),
                    "wilayah":   wilayah,
                    "kecamatan": safe_str(row.get("Kecamatan")),
                    "alamat":    safe_str(row.get("Alamat_Lengkap")),
                    "lat":       safe_float(row.get("Latitude")),
                    "lon":       safe_float(row.get("Longitude")),
                    "konsep":    safe_str(row.get("Konsep_Suasana")),
                    "target":    safe_str(row.get("Target_Pengunjung")),
                    "cocok":     safe_str(row.get("Cocok_Untuk")),
                    "menu_bs":   safe_str(row.get("Menu_Best_Seller")),
                    "harga_min": safe_int(row.get("Harga_Menu_Min")),
                    "harga_max": safe_int(row.get("Harga_Menu_Max")),
                    "jam_buka":  parse_time(row.get("Jam_Buka")),
                    "jam_tutup": parse_time(row.get("Jam_Tutup")),
                    "kapasitas": safe_int(row.get("Kapasitas_Orang")),
                    "fasilitas": fasilitas,
                    "batas_duduk": safe_str(row.get("Batas_Waktu_Duduk")),
                    "rating":    safe_float(row.get("Rating_Google")),
                    "min_order": safe_int(row.get("Minimal_Order")),
                    "gmaps":     safe_str(row.get("Link_Google_Maps")),
                    "kontak":    safe_str(row.get("Kontak_HP")),
                    "gambar":    [],
                    "sumber":    safe_str(row.get("Sumber_Data")),
                    "status":    "aktif",
                })
            inserted += 1

    await session.commit()
    return inserted, skipped

# ── Seed Admin User ────────────────────────────────────────────────────────────

async def seed_admin(session: AsyncSession):
    """Insert 1 akun admin default jika belum ada (menggunakan bcrypt)."""
    import bcrypt
    
    # 1. Cek apakah admin sudah ada
    res = await session.execute(
        text("SELECT password_hash FROM users WHERE email = 'admin@smarttourism.id'")
    )
    row = res.fetchone()
    
    if row:
        pwd_hash = row.password_hash
        # Jika hash tidak diawali $2b$ (bukan bcrypt), kita hapus dan buat ulang
        if not pwd_hash.startswith("$2b$"):
            print("  [INFO] Hash admin lama terdeteksi (SHA256), mereset ke bcrypt...")
            await session.execute(text("DELETE FROM users WHERE email = 'admin@smarttourism.id'"))
            await session.commit()
        else:
            print("  [SKIP] Admin user sudah ada dengan hash bcrypt.")
            return

    # 2. Buat hash baru menggunakan bcrypt
    pw_plain = "admin123"
    salt = bcrypt.gensalt()
    pw_hash = bcrypt.hashpw(pw_plain.encode("utf-8"), salt).decode("utf-8")

    await session.execute(text("""
        INSERT INTO users (nama, email, password_hash, role, is_active)
        VALUES ('Super Admin', 'admin@smarttourism.id', :pw, 'admin', true)
    """), {"pw": pw_hash})
    await session.commit()
    print("  [OK] Admin user dibuat: admin@smarttourism.id / admin123")
    print("  [OK] Admin user dibuat: admin@smarttourism.id / admin123")


# ── Seed Sentiment ────────────────────────────────────────────────────────────

async def seed_sentiment(session: AsyncSession) -> tuple[int, int]:
    """
    Seed data sentimen dari data/scrap/result/hasil_sentimen_{Wilayah}.xlsx
    untuk 4 wilayah: Indramayu, Cirebon, Majalengka, Kuningan.

    Kolom Excel yang digunakan:
      tempat_nama    → untuk lookup ke tabel wisata/kuliner/nongkrong
      wilayah        → untuk filter lookup (agar tidak bentrok nama sama beda wilayah)
      tipe_tempat    → 'Kuliner'/'Wisata'/'Nongkrong' → dinormalisasi ke lowercase
      teks_asli      → ulasan_asli (NOT NULL)
      teks_bersih    → ulasan_bersih
      sentimen_pred  → sentimen (positif/negatif/netral)
      confidence_pred→ confidence NUMERIC(5,4)

    model_used = 'indobert' (hasil fine-tuning IndoBERT di Colab).
    Idempotent — skip baris duplikat berdasarkan (tempat_kode + ulasan_asli).
    """
    inserted  = 0
    skipped   = 0
    not_found = 0

    WILAYAH = ["Indramayu", "Cirebon", "Majalengka", "Kuningan"]

    for w in WILAYAH:
        file_path = Path(f"data/scrap/result/hasil_sentimen_{w}.xlsx")

        if not file_path.exists():
            print(f"  [SKIP] File tidak ditemukan: {file_path}")
            continue

        print(f"  Memproses: {file_path} ...")
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            print(f"  [ERROR] Gagal membaca {file_path}: {e}")
            continue

        fi, fs, fn = 0, 0, 0

        for _, row in df.iterrows():
            ulasan_asli = safe_str(row.get("teks_asli"))
            if not ulasan_asli:
                continue

            tempat_nama   = safe_str(row.get("tempat_nama"))
            wilayah_val   = safe_str(row.get("wilayah", w))
            tipe_tempat   = safe_str(row.get("tipe_tempat", "wisata")).lower().strip()
            ulasan_bersih = safe_str(row.get("teks_bersih"))

            # Sentimen — hanya nilai valid enum DB: positif / negatif / netral
            sentimen_raw = safe_str(row.get("sentimen_pred"), "netral").lower().strip()
            sentimen = sentimen_raw if sentimen_raw in ("positif", "negatif", "netral") else "netral"

            # Confidence — NUMERIC(5,4): range 0.0000 – 0.9999
            confidence = round(
                max(0.0, min(0.9999, safe_float(row.get("confidence_pred"), 0.5) or 0.5)),
                4
            )

            # Validasi tipe_tempat sesuai enum DB
            if tipe_tempat not in ("wisata", "kuliner", "nongkrong"):
                fn += 1
                continue

            if not tempat_nama:
                fn += 1
                continue

            # Lookup tempat_id + kode dari DB menggunakan nama + wilayah
            q = await session.execute(
                text(f"""
                    SELECT id, kode FROM {tipe_tempat}
                    WHERE LOWER(nama) = LOWER(:nama)
                      AND wilayah     = :wilayah
                    LIMIT 1
                """),
                {"nama": tempat_nama, "wilayah": wilayah_val},
            )
            row_db = q.fetchone()
            
            # Fallback 1: Cari di semua tabel jika tipe_tempat salah di Excel
            if not row_db:
                q = await session.execute(
                    text("""
                        SELECT id, kode, tipe_tempat FROM (
                            SELECT id, kode, 'wisata' as tipe_tempat, nama, wilayah FROM wisata
                            UNION ALL
                            SELECT id, kode, 'kuliner' as tipe_tempat, nama, wilayah FROM kuliner
                            UNION ALL
                            SELECT id, kode, 'nongkrong' as tipe_tempat, nama, wilayah FROM nongkrong
                        ) t
                        WHERE LOWER(nama) = LOWER(:nama) AND wilayah = :wilayah
                        LIMIT 1
                    """),
                    {"nama": tempat_nama, "wilayah": wilayah_val},
                )
                row_db = q.fetchone()
                if row_db:
                    tipe_tempat = row_db[2]

            # Fallback 2: Pencarian menggunakan LIKE (mengabaikan sedikit perbedaan nama)
            if not row_db:
                q = await session.execute(
                    text("""
                        SELECT id, kode, tipe_tempat FROM (
                            SELECT id, kode, 'wisata' as tipe_tempat, nama, wilayah FROM wisata
                            UNION ALL
                            SELECT id, kode, 'kuliner' as tipe_tempat, nama, wilayah FROM kuliner
                            UNION ALL
                            SELECT id, kode, 'nongkrong' as tipe_tempat, nama, wilayah FROM nongkrong
                        ) t
                        WHERE LOWER(nama) LIKE LOWER(:nama_like) AND wilayah = :wilayah
                        LIMIT 1
                    """),
                    {"nama_like": f"%{tempat_nama}%", "wilayah": wilayah_val},
                )
                row_db = q.fetchone()
                if row_db:
                    tipe_tempat = row_db[2]

            if not row_db:
                fn += 1
                continue

            tempat_id   = row_db[0]
            tempat_kode = row_db[1]

            # Cek duplikat
            dup = await session.execute(
                text("""SELECT 1 FROM sentiment_results
                        WHERE tempat_kode = :kode
                          AND ulasan_asli = :ulasan
                        LIMIT 1"""),
                {"kode": tempat_kode, "ulasan": ulasan_asli},
            )
            if dup.fetchone():
                fs += 1
                continue

            # Insert — kolom sesuai skema sentiment_results di 01_schema.sql
            await session.execute(text("""
                INSERT INTO sentiment_results (
                    tipe_tempat, tempat_id, tempat_kode,
                    ulasan_asli, ulasan_bersih,
                    sentimen, confidence, model_used,
                    sumber_scraping, scraped_at
                ) VALUES (
                    :tipe, :tid, :kode,
                    :asli, :bersih,
                    :sentimen, :conf, 'indobert',
                    'excel_seed', NOW()
                )
            """), {
                "tipe":     tipe_tempat,
                "tid":      tempat_id,
                "kode":     tempat_kode,
                "asli":     ulasan_asli,
                "bersih":   ulasan_bersih,
                "sentimen": sentimen,
                "conf":     confidence,
            })
            fi += 1

        await session.commit()
        print(f"    [{w}] Inserted: {fi} | Duplikat: {fs} | Tidak ditemukan di DB: {fn}")
        inserted  += fi
        skipped   += fs
        not_found += fn

    print(f"\n  Total sentimen — Inserted: {inserted} | Duplikat: {skipped} | Tdk ditemukan: {not_found}")
    return inserted, skipped


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL tidak ditemukan di .env")
        sys.exit(1)

    print("=" * 55)
    print("  Smart Tourism — Database Seeder")
    print("=" * 55)

    async with AsyncSessionLocal() as session:
        print("\n[1/5] Seeding admin user...")
        await seed_admin(session)

        print("\n[2/5] Seeding wisata...")
        ins, skip = await seed_wisata(session)
        print(f"  [OK] Inserted: {ins} | Skipped (duplikat): {skip}")

        print("\n[3/5] Seeding kuliner...")
        ins, skip = await seed_kuliner(session)
        print(f"  [OK] Inserted: {ins} | Skipped (duplikat): {skip}")

        print("\n[4/5] Seeding nongkrong...")
        ins, skip = await seed_nongkrong(session)
        print(f"  [OK] Inserted: {ins} | Skipped (duplikat): {skip}")

        print("\n[5/5] Seeding hasil analisis sentimen...")
        ins, skip = await seed_sentiment(session)
        print(f"  [OK] Total inserted: {ins} | Duplikat: {skip}")

    print("\n" + "=" * 55)
    print("  Seeding selesai!")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
