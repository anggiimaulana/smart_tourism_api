-- ============================================================
--  03_fts.sql — Full-Text Search untuk Chatbot RAG
--  Jalankan SETELAH 01_schema.sql
--  psql -U postgres -d smart_tourism -f 03_fts.sql
-- ============================================================

-- Extension trigram untuk similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ── Tambah kolom tsvector ke tiap tabel ─────────────────────

ALTER TABLE wisata    ADD COLUMN IF NOT EXISTS fts tsvector;
ALTER TABLE kuliner   ADD COLUMN IF NOT EXISTS fts tsvector;
ALTER TABLE nongkrong ADD COLUMN IF NOT EXISTS fts tsvector;

-- ── Fungsi update FTS ────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_wisata_fts() RETURNS TRIGGER AS $$
BEGIN
  NEW.fts := to_tsvector('indonesian',
    coalesce(NEW.nama, '') || ' ' ||
    coalesce(NEW.wilayah::text, '') || ' ' ||
    coalesce(NEW.kecamatan, '') || ' ' ||
    coalesce(NEW.kategori_utama::text, '') || ' ' ||
    coalesce(NEW.sub_kategori, '') || ' ' ||
    coalesce(NEW.deskripsi, '') || ' ' ||
    coalesce(array_to_string(NEW.fasilitas, ' '), '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_kuliner_fts() RETURNS TRIGGER AS $$
BEGIN
  NEW.fts := to_tsvector('indonesian',
    coalesce(NEW.nama, '') || ' ' ||
    coalesce(NEW.wilayah::text, '') || ' ' ||
    coalesce(NEW.kecamatan, '') || ' ' ||
    coalesce(NEW.kategori_menu_utama, '') || ' ' ||
    coalesce(NEW.menu_unggulan, '') || ' ' ||
    coalesce(NEW.nama_makanan_khas, '') || ' ' ||
    coalesce(array_to_string(NEW.fasilitas, ' '), '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_nongkrong_fts() RETURNS TRIGGER AS $$
BEGIN
  NEW.fts := to_tsvector('indonesian',
    coalesce(NEW.nama, '') || ' ' ||
    coalesce(NEW.wilayah::text, '') || ' ' ||
    coalesce(NEW.kecamatan, '') || ' ' ||
    coalesce(NEW.konsep_suasana, '') || ' ' ||
    coalesce(NEW.cocok_untuk, '') || ' ' ||
    coalesce(NEW.menu_best_seller, '') || ' ' ||
    coalesce(array_to_string(NEW.fasilitas, ' '), '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── Pasang trigger ───────────────────────────────────────────

DROP TRIGGER IF EXISTS trig_wisata_fts    ON wisata;
DROP TRIGGER IF EXISTS trig_kuliner_fts   ON kuliner;
DROP TRIGGER IF EXISTS trig_nongkrong_fts ON nongkrong;

CREATE TRIGGER trig_wisata_fts
  BEFORE INSERT OR UPDATE ON wisata
  FOR EACH ROW EXECUTE FUNCTION update_wisata_fts();

CREATE TRIGGER trig_kuliner_fts
  BEFORE INSERT OR UPDATE ON kuliner
  FOR EACH ROW EXECUTE FUNCTION update_kuliner_fts();

CREATE TRIGGER trig_nongkrong_fts
  BEFORE INSERT OR UPDATE ON nongkrong
  FOR EACH ROW EXECUTE FUNCTION update_nongkrong_fts();

-- ── Index GIN untuk FTS + trigram ────────────────────────────

CREATE INDEX IF NOT EXISTS idx_wisata_fts    ON wisata    USING GIN(fts);
CREATE INDEX IF NOT EXISTS idx_kuliner_fts   ON kuliner   USING GIN(fts);
CREATE INDEX IF NOT EXISTS idx_nongkrong_fts ON nongkrong USING GIN(fts);

CREATE INDEX IF NOT EXISTS idx_wisata_nama_trgm    ON wisata    USING GIN(nama gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_kuliner_nama_trgm   ON kuliner   USING GIN(nama gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nongkrong_nama_trgm ON nongkrong USING GIN(nama gin_trgm_ops);

-- ── Refresh FTS untuk data yang sudah di-seed ────────────────
-- (jalankan ini sekali setelah seed selesai)

UPDATE wisata    SET fts = fts;   -- trigger akan re-compute
UPDATE kuliner   SET fts = fts;
UPDATE nongkrong SET fts = fts;

-- ── View gabungan untuk RAG retrieval ────────────────────────

CREATE OR REPLACE VIEW v_all_tempat AS
  SELECT
    id, kode, nama, 'wisata' AS tipe, wilayah::text, kecamatan,
    alamat_lengkap, latitude, longitude, deskripsi,
    harga_tiket_min AS harga_min, harga_tiket_max AS harga_max,
    jam_buka, jam_tutup, fasilitas, rating_google,
    link_google_maps, gambar, sentimen::text, skor_sentimen, fts
  FROM wisata WHERE status = 'aktif'

  UNION ALL

  SELECT
    id, kode, nama, 'kuliner' AS tipe, wilayah::text, kecamatan,
    alamat_lengkap, latitude, longitude,
    menu_unggulan AS deskripsi,
    harga_menu_min AS harga_min, harga_menu_max AS harga_max,
    jam_buka, jam_tutup, fasilitas, rating_google,
    link_google_maps, gambar, sentimen::text, skor_sentimen, fts
  FROM kuliner WHERE status = 'aktif'

  UNION ALL

  SELECT
    id, kode, nama, 'nongkrong' AS tipe, wilayah::text, kecamatan,
    alamat_lengkap, latitude, longitude,
    menu_best_seller AS deskripsi,
    harga_menu_min AS harga_min, harga_menu_max AS harga_max,
    jam_buka, jam_tutup, fasilitas, rating_google,
    link_google_maps, gambar, sentimen::text, skor_sentimen, fts
  FROM nongkrong WHERE status = 'aktif';
