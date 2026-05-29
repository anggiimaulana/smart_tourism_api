# 🗺️ Smart Tourism Ciayumajakuning — API

Backend AI-powered untuk sistem Smart Tourism wilayah **Ciayumajakuning**  
(Cirebon · Indramayu · Majalengka · Kuningan), Jawa Barat.

---

## 🤖 Sistem AI

| Sistem                                    | Teknologi                               | PIC    |
| ----------------------------------------- | --------------------------------------- | ------ |
| Analisis Sentimen — Indramayu & Cirebon   | IndoBERT + Scikit-learn                 | Anggi  |
| Analisis Sentimen — Majalengka & Kuningan | IndoBERT + Scikit-learn                 | Ikhsan |
| Chatbot RAG                               | PostgreSQL FTS + Gemini 1.5 Flash       | Vanes  |
| Rekomendasi & Planning                    | Collaborative Filtering + Content-Based | Rifqy  |

---

## 🏗️ Tech Stack

| Layer                | Teknologi                                                 |
| -------------------- | --------------------------------------------------------- |
| **Backend API**      | Python 3.10+, FastAPI 0.111, Uvicorn                      |
| **Database**         | PostgreSQL 15 (FTS via `tsvector` + `pg_trgm`)            |
| **ORM**              | SQLAlchemy 2.0 (async)                                    |
| **Auth**             | JWT (python-jose) + bcrypt                                |
| **AI — Sentimen**    | IndoBERT, Naive Bayes, SVM, Decision Tree                 |
| **AI — Chatbot**     | PostgreSQL FTS (retriever) + Gemini 1.5 Flash (generator) |
| **AI — Rekomendasi** | Surprise SVD + TF-IDF Cosine Similarity                   |
| **Testing**          | pytest + pytest-asyncio + httpx                           |

---

## 📁 Struktur Project

```
smart-tourism-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                         # Entry point, CORS, startup
│   │
│   ├── core/
│   │   ├── config.py                   # Settings dari .env
│   │   ├── database.py                 # Async engine + get_db()
│   │   └── security.py                 # JWT, bcrypt, auth guards
│   │
│   ├── models/                         # SQLAlchemy ORM (1 file per tabel)
│   │   ├── user.py
│   │   ├── wisata.py
│   │   ├── kuliner.py
│   │   ├── nongkrong.py
│   │   ├── sentiment_result.py
│   │   ├── user_history.py
│   │   ├── user_preference.py
│   │   ├── chatbot_session.py
│   │   └── planning_wisata.py
│   │
│   ├── schemas/                        # Pydantic v2 (request & response)
│   │   ├── base.py                     # BaseResponse, PaginatedResponse
│   │   ├── auth.py
│   │   ├── wisata.py
│   │   ├── kuliner.py
│   │   ├── nongkrong.py
│   │   ├── sentiment.py                # [Anggi & Ikhsan]
│   │   ├── chatbot.py                  # [Vanes]
│   │   └── recommendation.py          # [Rifqy]
│   │
│   ├── api/v1/
│   │   ├── router.py                   # Gabungkan semua endpoint
│   │   └── endpoints/
│   │       ├── auth.py                 # POST /auth/register, /login, GET /me
│   │       ├── wisata.py               # CRUD Wisata
│   │       ├── kuliner.py              # CRUD Kuliner
│   │       ├── nongkrong.py            # CRUD Nongkrong
│   │       ├── sentiment.py            # [Anggi & Ikhsan]
│   │       ├── chatbot.py              # [Vanes]
│   │       └── recommendation.py      # [Rifqy]
│   │
│   └── services/                       # Business logic & AI
│       ├── wisata_service.py
│       ├── kuliner_service.py
│       ├── nongkrong_service.py
│       ├── sentiment_service.py        # [Anggi & Ikhsan]
│       ├── chatbot_service.py          # [Vanes]
│       └── recommendation_service.py  # [Rifqy]
│
├── ml/                                 # Model AI (jangan di-commit!)
│   ├── sentiment/
│   │   ├── model/                      # IndoBERT weights (dari Colab)
│   │   └── baseline/                   # naive_bayes.pkl, svm.pkl, dt.pkl
│   └── recommendation/
│       ├── cf_model.pkl                # SVD model (dari Colab)
│       ├── tfidf_vectorizer.pkl
│       ├── tfidf_matrix.pkl
│       └── items_df.pkl
│
├── data/                               # Dataset Excel (jangan di-commit!)
│   ├── Wisata.xlsx
│   ├── Kuliner.xlsx
│   └── Nongkrong.xlsx
│
├── sql/
│   ├── 01_schema.sql                   # DDL: 10 tabel + enum + trigger + index
│   ├── 02_seed.py                      # Import Excel → PostgreSQL (idempotent)
│   └── 03_fts.sql                      # Full-Text Search: tsvector, GIN index
│
├── scripts/
│   ├── colab/
│   │   ├── sentiment_training.ipynb    # [Anggi & Ikhsan] Training di Colab GPU
│   │   └── recommendation_training.ipynb  # [Rifqy] Training di Colab GPU
│   └── utils/
│       ├── check_db.py                 # Verifikasi koneksi & jumlah data
│       ├── reset_db.py                 # Drop + recreate semua tabel (dev only)
│       └── export_sentiment.py        # Export sentiment_results ke Excel
│
├── prompts/
│   └── chatbot_prompts.py              # System prompt + template Gemini
│
├── tests/
│   ├── conftest.py                     # Fixture: async client, DB session, token
│   ├── test_auth.py
│   ├── test_wisata.py
│   ├── test_sentiment.py
│   ├── test_chatbot.py
│   └── test_recommendation.py
│
├── .env                                # JANGAN di-commit
├── .env.example                        # Template env untuk tim
├── .gitignore
├── requirements.txt
├── CONTRIBUTING.md
└── README.md
```

---

## 🚀 Setup & Menjalankan

### 1. Clone & Virtual Environment

```bash
git clone <url-repo>
cd smart-tourism-api

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Konfigurasi Environment

```bash
copy .env.example .env
# Edit .env — isi DATABASE_URL, GEMINI_API_KEY, SECRET_KEY
```

### 3. Setup Database

```bash
# Buat database PostgreSQL
psql -U postgres -c "CREATE DATABASE smart_tourism ENCODING 'UTF8'"

# Jalankan schema, FTS, lalu seed (URUTAN WAJIB)
psql -U postgres -d smart_tourism -f sql/01_schema.sql
psql -U postgres -d smart_tourism -f sql/03_fts.sql

# Letakkan file Excel di folder data/ lalu:
python sql/02_seed.py

# Verifikasi data masuk
python scripts/utils/check_db.py
```

Catatan seeding: file Excel akan dibaca dari semua sheet, bukan hanya sheet pertama. Jadi data dari `indramayu`, `cirebon`, `majalengka`, dan `kuningan` ikut masuk.

### 4. Migration dengan Alembic

Kalau tim mau perubahan skema dikelola lewat migration history, pakai Alembic.
Di repo ini Alembic belum aktif, jadi setup dasarnya seperti ini:

```bash
pip install alembic
alembic init alembic
```

Lalu arahkan `DATABASE_URL` ke `.env`, set `target_metadata = Base.metadata`, dan sesuaikan `alembic/env.py` untuk async engine.

Revision awal:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Catatan cache chatbot:

- Tabel `chatbot_cache` harus datang dari bootstrap schema atau migration Alembic, bukan dibuat saat request berjalan.
- Saat `alembic upgrade head`, migration `2c4f7a9b6d10_add_chatbot_cache_table.py` akan membuat tabel tersebut.
- Saat reset database dengan `python scripts/utils/reset_db.py`, file `sql/01_schema.sql` juga membuat `chatbot_cache` secara otomatis.

### 5. Reset + Seed seperti Laravel

Kalau ingin reset database lalu migrate dan seed lagi dalam satu perintah, jalankan:

```bash
python scripts/utils/reset_db.py
```

Script ini akan drop schema aktif, menjalankan schema + FTS, lalu seeding data dari `data/`.
Di dalam schema bootstrap tersebut sudah termasuk `chatbot_cache`, jadi setelah reset database cache table langsung tersedia tanpa langkah tambahan.

### 6. Jalankan Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

| URL                           | Keterangan              |
| ----------------------------- | ----------------------- |
| `http://localhost:8001`       | Health check            |
| `http://localhost:8001/docs`  | Swagger UI (DEBUG mode) |
| `http://localhost:8001/redoc` | ReDoc                   |

---

## 🧪 Menjalankan Test

```bash
# Install test dependencies (sudah ada di requirements.txt)

# Jalankan semua test
pytest tests/ -v

# Jalankan per modul
pytest tests/test_auth.py -v
pytest tests/test_wisata.py -v
pytest tests/test_sentiment.py -v
pytest tests/test_chatbot.py -v
pytest tests/test_recommendation.py -v
```

> Test menggunakan database **terpisah** `smart_tourism_test`. Buat dulu:
> `psql -U postgres -c "CREATE DATABASE smart_tourism_test"`

---

## 📋 Ringkasan Endpoint

### Auth

| Method | Endpoint                | Auth    | Deskripsi                  |
| ------ | ----------------------- | ------- | -------------------------- |
| POST   | `/api/v1/auth/register` | ❌      | Registrasi pengunjung baru |
| POST   | `/api/v1/auth/login`    | ❌      | Login → JWT token          |
| GET    | `/api/v1/auth/me`       | 🔑 User | Profil user aktif          |

### Data (Wisata / Kuliner / Nongkrong — pola sama)

| Method | Endpoint                | Auth     | Deskripsi                       |
| ------ | ----------------------- | -------- | ------------------------------- |
| GET    | `/api/v1/wisata/`       | ❌       | List dengan filter & pagination |
| GET    | `/api/v1/wisata/{kode}` | ❌       | Detail satu tempat              |
| POST   | `/api/v1/wisata/`       | 🔒 Admin | Tambah baru                     |
| PATCH  | `/api/v1/wisata/{kode}` | 🔒 Admin | Update sebagian                 |
| DELETE | `/api/v1/wisata/{kode}` | 🔒 Admin | Hapus                           |

### AI — Sentimen

| Method | Endpoint                               | Auth     | Deskripsi                     |
| ------ | -------------------------------------- | -------- | ----------------------------- |
| POST   | `/api/v1/sentiment/predict`            | ❌       | Prediksi satu ulasan          |
| POST   | `/api/v1/sentiment/predict/batch`      | ❌       | Prediksi massal (maks. 100)   |
| GET    | `/api/v1/sentiment/summary/{wilayah}`  | ❌       | Ringkasan agregat per wilayah |
| POST   | `/api/v1/sentiment/sync/{tipe}/{kode}` | 🔒 Admin | Sinkronisasi ke tabel utama   |

### AI — Chatbot RAG

| Method | Endpoint                          | Auth | Deskripsi                            |
| ------ | --------------------------------- | ---- | ------------------------------------ |
| POST   | `/api/v1/chatbot/ask`             | ❌   | Tanya chatbot (new/continue session) |
| GET    | `/api/v1/chatbot/history/{token}` | ❌   | Riwayat percakapan                   |
| DELETE | `/api/v1/chatbot/history/{token}` | ❌   | Reset sesi                           |

### AI — Rekomendasi & Planning

| Method | Endpoint                          | Auth          | Deskripsi                           |
| ------ | --------------------------------- | ------------- | ----------------------------------- |
| POST   | `/api/v1/recommendation/`         | ❌ (optional) | Rekomendasi personal/popular/nearby |
| POST   | `/api/v1/recommendation/planning` | ❌ (optional) | Buat itinerary otomatis             |
| POST   | `/api/v1/recommendation/history`  | ❌            | Catat interaksi user                |

---

## 🔀 Arsitektur RAG Chatbot (CPU-Friendly)

```
User Query
    │
    ▼
[1] Deteksi wilayah dari teks atau koordinat GPS (haversine)
    │
    ▼
[2] PostgreSQL Full-Text Search
    tsvector + pg_trgm → top-5 dokumen relevan
    Fallback: ILIKE similarity jika FTS kosong
    │
    ▼
[3] Context Builder
    Format dokumen → string konteks terstruktur
    │
    ▼
[4] Gemini 1.5 Flash
    System prompt + konteks + riwayat + pertanyaan → jawaban
    │
    ▼
[5] Response + referensi tempat + simpan ke chatbot_sessions
```

**Keuntungan:** Tidak butuh FAISS / ChromaDB / embedding model.  
Semua berjalan di CPU, cocok untuk VS Code development.

Catatan implementasi saat ini:

- Respons statis seperti identitas, error umum, dan penolakan out-of-scope ditangani deterministik tanpa memanggil LLM.
- Payload FastAPI yang dianggap source of truth adalah wrapper `BaseResponse` dengan isi utama di field `data`.
- Implementasi retrieval, session management, dan cache exact-match ada di `app/services/chatbot_service.py`.
- Mode LLM bisa diaktifkan lagi sebagai opsi saat dibutuhkan jawaban yang lebih natural untuk pertanyaan generatif, tetapi jalur deterministik tetap dipertahankan sebagai fallback utama.

---

## 🧠 Training Model (Google Colab)

```
scripts/colab/sentiment_training.ipynb      → Anggi & Ikhsan
scripts/colab/recommendation_training.ipynb → Rifqy
```

Setelah training → download dari Google Drive → letakkan di `ml/`.  
File model **tidak di-commit** ke GitHub (sudah ada di `.gitignore`).

---

## 🛠️ Scripts Utility

```bash
python scripts/utils/check_db.py              # cek koneksi & jumlah data
python scripts/utils/reset_db.py              # reset DB (dev only, butuh konfirmasi)
python scripts/utils/export_sentiment.py               # export semua sentimen
python scripts/utils/export_sentiment.py Indramayu     # export per wilayah
```

---

## 👥 Kontribusi

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk panduan branch, commit message, dan checklist PR.

### Branch per Anggota

```
develop
  ├── feature/sentiment-anggi       ← Anggi
  ├── feature/sentiment-ikhsan      ← Ikhsan
  ├── feature/chatbot-vanes         ← Vanes
  └── feature/recommendation-rifqy  ← Rifqy
```
