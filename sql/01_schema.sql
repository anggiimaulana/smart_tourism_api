-- ============================================================
--  SMART TOURISM CIAYUMAJAKUNING — DATABASE SCHEMA
--  File    : 01_schema.sql
--  Jalankan: psql -U postgres -d smart_tourism -f 01_schema.sql
-- ============================================================

-- Buat database (jalankan sekali, sebagai superuser)
-- CREATE DATABASE smart_tourism ENCODING 'UTF8';

-- Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- ────────────────────────────────────────────────────────────
-- ENUM TYPES
-- ────────────────────────────────────────────────────────────
CREATE TYPE wilayah_enum       AS ENUM ('Indramayu','Cirebon','Majalengka','Kuningan');
CREATE TYPE sentimen_enum      AS ENUM ('positif','negatif','netral');
CREATE TYPE role_enum          AS ENUM ('admin','pengunjung');
CREATE TYPE status_enum        AS ENUM ('aktif','nonaktif','draft');
CREATE TYPE kategori_wisata    AS ENUM ('Alam','Buatan','Budaya','Religi','Petualangan','Edukasi','Lainnya');
CREATE TYPE model_sentimen     AS ENUM ('indobert','naive_bayes','svm','decision_tree');
CREATE TYPE tipe_tempat_enum   AS ENUM ('wisata','kuliner','nongkrong');
CREATE TYPE jenis_kuliner_enum AS ENUM ('Restoran','Warung','Cafe','Kedai','Food Court','Angkringan','Lainnya');

-- ────────────────────────────────────────────────────────────
-- 1. USERS
-- ────────────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nama            VARCHAR(150)        NOT NULL,
    email           VARCHAR(255)        NOT NULL UNIQUE,
    password_hash   TEXT                NOT NULL,
    role            role_enum           NOT NULL DEFAULT 'pengunjung',
    avatar_url      TEXT,
    is_active       BOOLEAN             NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email  ON users(email);
CREATE INDEX idx_users_role   ON users(role);

-- ────────────────────────────────────────────────────────────
-- 2. WISATA
-- ────────────────────────────────────────────────────────────
CREATE TABLE wisata (
    id                      SERIAL PRIMARY KEY,
    uid                     UUID                 NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    kode                    VARCHAR(20)          NOT NULL UNIQUE,   -- WIS-IDM-001
    nama                    VARCHAR(255)         NOT NULL,
    wilayah                 wilayah_enum         NOT NULL,
    kecamatan               VARCHAR(100),
    alamat_lengkap          TEXT,
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    kategori_utama          kategori_wisata,
    sub_kategori            VARCHAR(100),
    jenis_tempat            VARCHAR(100),
    deskripsi               TEXT,
    harga_tiket_min         INTEGER              DEFAULT 0,
    harga_tiket_max         INTEGER              DEFAULT 0,
    gratis                  BOOLEAN              DEFAULT FALSE,
    jam_buka                TIME,
    jam_tutup               TIME,
    hari_libur_operasional  VARCHAR(255),
    estimasi_durasi_jam     NUMERIC(4,1),
    fasilitas               TEXT[],              -- array string
    aksesibilitas           VARCHAR(100),
    moda_transportasi       VARCHAR(255),
    rating_google           NUMERIC(3,1),
    jumlah_ulasan_google    INTEGER              DEFAULT 0,
    link_google_maps        TEXT,
    link_instagram          TEXT,
    link_website            TEXT,
    kontak                  TEXT,
    gambar                  TEXT[],              -- array URL gambar (ganti Drive ID)
    sumber_data             TEXT,
    diinput_oleh            VARCHAR(100),
    status                  status_enum          NOT NULL DEFAULT 'draft',
    -- kolom AI (diisi otomatis oleh sistem)
    sentimen                sentimen_enum,
    skor_sentimen           NUMERIC(5,4),        -- 0.0000 – 1.0000
    total_ulasan_scraped    INTEGER              DEFAULT 0,
    total_positif           INTEGER              DEFAULT 0,
    total_negatif           INTEGER              DEFAULT 0,
    created_at              TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ          NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_wisata_wilayah   ON wisata(wilayah);
CREATE INDEX idx_wisata_kategori  ON wisata(kategori_utama);
CREATE INDEX idx_wisata_sentimen  ON wisata(sentimen);
CREATE INDEX idx_wisata_rating    ON wisata(rating_google);
CREATE INDEX idx_wisata_lokasi    ON wisata(latitude, longitude);
CREATE INDEX idx_wisata_uid       ON wisata(uid);

-- ────────────────────────────────────────────────────────────
-- 3. KULINER
-- ────────────────────────────────────────────────────────────
CREATE TABLE kuliner (
    id                      SERIAL PRIMARY KEY,
    uid                     UUID                 NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    kode                    VARCHAR(20)          NOT NULL UNIQUE,   -- KUL-IDM-001
    id_wisata_terdekat      VARCHAR(20)          REFERENCES wisata(kode) ON DELETE SET NULL,
    nama                    VARCHAR(255)         NOT NULL,
    wilayah                 wilayah_enum         NOT NULL,
    kecamatan               VARCHAR(100),
    alamat_lengkap          TEXT,
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    jenis_tempat            jenis_kuliner_enum,
    kategori_menu_utama     VARCHAR(100),
    menu_unggulan           TEXT,
    makanan_khas_daerah     BOOLEAN              DEFAULT FALSE,
    nama_makanan_khas       VARCHAR(255),
    harga_menu_min          INTEGER              DEFAULT 0,
    harga_menu_max          INTEGER              DEFAULT 0,
    jam_buka                TIME,
    jam_tutup               TIME,
    kapasitas_orang         INTEGER,
    fasilitas               TEXT[],
    sertifikat_halal        BOOLEAN              DEFAULT FALSE,
    rating_google           NUMERIC(3,1),
    jumlah_ulasan_google    INTEGER              DEFAULT 0,
    link_google_maps        TEXT,
    kontak                  TEXT,
    gambar                  TEXT[],              -- array URL gambar
    sumber_data             TEXT,
    catatan                 TEXT,
    status                  status_enum          NOT NULL DEFAULT 'draft',
    -- kolom AI
    sentimen                sentimen_enum,
    skor_sentimen           NUMERIC(5,4),
    total_ulasan_scraped    INTEGER              DEFAULT 0,
    total_positif           INTEGER              DEFAULT 0,
    total_negatif           INTEGER              DEFAULT 0,
    created_at              TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ          NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kuliner_wilayah   ON kuliner(wilayah);
CREATE INDEX idx_kuliner_sentimen  ON kuliner(sentimen);
CREATE INDEX idx_kuliner_lokasi    ON kuliner(latitude, longitude);
CREATE INDEX idx_kuliner_uid       ON kuliner(uid);

-- ────────────────────────────────────────────────────────────
-- 4. NONGKRONG
-- ────────────────────────────────────────────────────────────
CREATE TABLE nongkrong (
    id                  SERIAL PRIMARY KEY,
    uid                 UUID                 NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    kode                VARCHAR(20)          NOT NULL UNIQUE,   -- NGK-IDM-001
    id_wisata_ref       VARCHAR(20)          REFERENCES wisata(kode) ON DELETE SET NULL,
    nama                VARCHAR(255)         NOT NULL,
    wilayah             wilayah_enum         NOT NULL,
    kecamatan           VARCHAR(100),
    alamat_lengkap      TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    konsep_suasana      VARCHAR(255),
    target_pengunjung   VARCHAR(100),
    cocok_untuk         VARCHAR(255),
    menu_best_seller    TEXT,
    harga_menu_min      INTEGER              DEFAULT 0,
    harga_menu_max      INTEGER              DEFAULT 0,
    jam_buka            TIME,
    jam_tutup           TIME,
    kapasitas_orang     INTEGER,
    fasilitas           TEXT[],
    batas_waktu_duduk   VARCHAR(100),
    rating_google       NUMERIC(3,1),
    minimal_order       INTEGER              DEFAULT 0,
    link_google_maps    TEXT,
    kontak              TEXT,
    gambar              TEXT[],              -- array URL gambar
    sumber_data         TEXT,
    catatan             TEXT,
    status              status_enum          NOT NULL DEFAULT 'draft',
    -- kolom AI
    sentimen            sentimen_enum,
    skor_sentimen       NUMERIC(5,4),
    total_ulasan_scraped INTEGER             DEFAULT 0,
    total_positif       INTEGER              DEFAULT 0,
    total_negatif       INTEGER              DEFAULT 0,
    created_at          TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ          NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nongkrong_wilayah   ON nongkrong(wilayah);
CREATE INDEX idx_nongkrong_sentimen  ON nongkrong(sentimen);
CREATE INDEX idx_nongkrong_lokasi    ON nongkrong(latitude, longitude);
CREATE INDEX idx_nongkrong_uid       ON nongkrong(uid);

-- ────────────────────────────────────────────────────────────
-- 5. SENTIMENT RESULTS  (hasil scraping + prediksi model)
-- ────────────────────────────────────────────────────────────
CREATE TABLE sentiment_results (
    id              SERIAL PRIMARY KEY,
    tipe_tempat     tipe_tempat_enum    NOT NULL,
    tempat_id       INTEGER             NOT NULL,   -- FK logis ke wisata/kuliner/nongkrong
    tempat_kode     VARCHAR(20)         NOT NULL,
    ulasan_asli     TEXT                NOT NULL,
    ulasan_bersih   TEXT,                           -- setelah preprocessing
    sentimen        sentimen_enum       NOT NULL,
    confidence      NUMERIC(5,4)        NOT NULL,
    model_used      model_sentimen      NOT NULL,
    sumber_scraping VARCHAR(100),                   -- 'google_maps','tripadvisor',dll
    scraped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sr_tempat      ON sentiment_results(tipe_tempat, tempat_id);
CREATE INDEX idx_sr_sentimen    ON sentiment_results(sentimen);
CREATE INDEX idx_sr_model       ON sentiment_results(model_used);

-- ────────────────────────────────────────────────────────────
-- 6. USER HISTORY  (tracking untuk rekomendasi)
-- ────────────────────────────────────────────────────────────
CREATE TABLE user_history (
    id              SERIAL PRIMARY KEY,
    user_id         UUID                NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tipe_tempat     tipe_tempat_enum    NOT NULL,
    tempat_id       INTEGER             NOT NULL,
    tempat_kode     VARCHAR(20)         NOT NULL,
    aksi            VARCHAR(30)         NOT NULL CHECK (aksi IN ('klik','kunjungi','simpan','rating','share')),
    nilai_rating    NUMERIC(2,1)        CHECK (nilai_rating BETWEEN 1.0 AND 5.0),
    durasi_detik    INTEGER,            -- lama user di halaman detail (untuk sinyal engagement)
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_uh_user        ON user_history(user_id);
CREATE INDEX idx_uh_tempat      ON user_history(tipe_tempat, tempat_id);
CREATE INDEX idx_uh_aksi        ON user_history(aksi);

-- ────────────────────────────────────────────────────────────
-- 7. USER PREFERENCES  (preferensi eksplisit user)
-- ────────────────────────────────────────────────────────────
CREATE TABLE user_preferences (
    id                  SERIAL PRIMARY KEY,
    user_id             UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    kategori_favorit    TEXT[],         -- ['Alam','Budaya']
    wilayah_favorit     TEXT[],         -- ['Indramayu','Cirebon']
    budget_min          INTEGER         DEFAULT 0,
    budget_max          INTEGER         DEFAULT 0,
    tipe_wisata         TEXT[],         -- preferensi jenis wisata
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 8. CHATBOT SESSIONS  (history percakapan per user)
-- ────────────────────────────────────────────────────────────
CREATE TABLE chatbot_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            REFERENCES users(id) ON DELETE SET NULL,
    session_token   VARCHAR(100)    NOT NULL UNIQUE,
    messages        JSONB           NOT NULL DEFAULT '[]',   -- [{role,content,timestamp}]
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    wilayah_terdeteksi wilayah_enum,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cs_user    ON chatbot_sessions(user_id);
CREATE INDEX idx_cs_token   ON chatbot_sessions(session_token);

-- ────────────────────────────────────────────────────────────
-- 8b. CHATBOT CACHE  (exact-match cache untuk jawaban chatbot)
-- ────────────────────────────────────────────────────────────
CREATE TABLE chatbot_cache (
    id                  UUID            PRIMARY KEY,
    query_hash          VARCHAR(128)    NOT NULL UNIQUE,
    query_normalized     TEXT            NOT NULL,
    answer              JSONB           NOT NULL,
    hit_count           INTEGER         NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chatbot_cache_query_hash ON chatbot_cache(query_hash);

-- ────────────────────────────────────────────────────────────
-- 9. PLANNING WISATA  (itinerary yang dibuat user)
-- ────────────────────────────────────────────────────────────
CREATE TABLE planning_wisata (
    id              SERIAL PRIMARY KEY,
    user_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    judul           VARCHAR(255)    NOT NULL,
    wilayah         TEXT[],         -- bisa multi-wilayah
    tanggal_mulai   DATE,
    tanggal_selesai DATE,
    jumlah_orang    INTEGER         DEFAULT 1,
    budget_total    INTEGER,
    catatan         TEXT,
    items           JSONB           NOT NULL DEFAULT '[]',
    -- items: [{hari, urutan, tipe_tempat, tempat_id, tempat_kode, nama, jam_kunjungan, catatan}]
    status          VARCHAR(30)     DEFAULT 'draft' CHECK (status IN ('draft','finalized','selesai')),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pw_user ON planning_wisata(user_id);

-- ────────────────────────────────────────────────────────────
-- 10. TRIGGER: auto update updated_at
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Pasang trigger ke semua tabel yang punya updated_at
DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['users','wisata','kuliner','nongkrong','chatbot_sessions','chatbot_cache','planning_wisata','user_preferences']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER set_updated_at BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()', tbl
        );
    END LOOP;
END;
$$;
