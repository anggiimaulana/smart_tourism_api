-- ============================================================
--  04_reviews.sql — TABEL ULASAN (REVIEWS)
--  Jalankan setelah 01_schema.sql dan 03_fts.sql
-- ============================================================

CREATE TABLE reviews (
    id          UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID            NOT NULL,
    tempat_id   UUID            NOT NULL,
    rating      INTEGER         NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment     TEXT,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINT RELASI (FOREIGN KEY)
    -- Menghubungkan user_id ke tabel users asli di proyekmu
    CONSTRAINT fk_reviews_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
    
    -- Catatan: tempat_id tidak di-foreign key langsung ke v_all_tempat 
    -- karena v_all_tempat adalah VIEW (bukan tabel fisik). 
    -- Namun tipe datanya sudah sama-sama UUID sehingga aman dan efisien saat JOIN.
);

-- Buat Index agar proses pencarian ulasan berdasarkan tempat atau user jadi super cepat
CREATE INDEX idx_reviews_tempat ON reviews(tempat_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);

-- Pasang trigger auto-update updated_at (memanfaatkan fungsi yang sudah ada di 01_schema.sql)
CREATE TRIGGER set_updated_at_reviews
BEFORE UPDATE ON reviews
FOR EACH ROW
EXECUTE FUNCTION trigger_set_updated_at();