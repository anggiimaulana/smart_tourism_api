# Panduan Inisiasi Smart Tourism API

Dokumen ini merangkum langkah awal untuk menyiapkan project, mulai dari clone repo sampai seeding database dan menjalankan aplikasi.

## 1. Prasyarat

- Python 3.10+.
- PostgreSQL 15+.
- Git.
- File model AI di folder `ml/` jika ingin menjalankan fitur sentimen, chatbot, atau rekomendasi penuh.

## 2. Clone Repo

```bash
git clone <url-repo>
cd smart-tourism-api
```

## 3. Buat Virtual Environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Jika PowerShell menolak aktivasi, jalankan sekali:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## 4. Install Dependency

```bash
pip install -r requirements.txt
```

## 5. Siapkan File Environment

Salin `.env.example` menjadi `.env`, lalu isi variabel penting berikut:

- `DATABASE_URL`
- `GEMINI_API_KEY`
- `SECRET_KEY`

Contoh format `DATABASE_URL`:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
```

## 6. Buat Database PostgreSQL

```bash
psql -U postgres -c "CREATE DATABASE smart_tourism ENCODING 'UTF8'"
psql -U postgres -c "CREATE DATABASE smart_tourism_test ENCODING 'UTF8'"
```

## 7. Jalankan Schema dan FTS

Urutan ini wajib agar struktur tabel dan full-text search aktif.

```bash
psql -U postgres -d smart_tourism -f sql/01_schema.sql
psql -U postgres -d smart_tourism -f sql/03_fts.sql
```

## 8. Opsional: Migration dengan Alembic

Kalau tim ingin migration yang lebih rapi dari perubahan model SQLAlchemy ke PostgreSQL, gunakan Alembic.
Di repo ini Alembic belum diset up, jadi langkah di bawah adalah standar yang disarankan.

```bash
pip install alembic
alembic init alembic
```

Setelah itu:

1. Arahkan `sqlalchemy.url` ke `DATABASE_URL` dari `.env`.
2. Set `target_metadata = Base.metadata` dari `app/core/database.py`.
3. Sesuaikan `alembic/env.py` untuk async engine.
4. Buat revision pertama:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Kalau ada perubahan model di kemudian hari, ulangi pola ini:

```bash
alembic revision --autogenerate -m "nama perubahan"
alembic upgrade head
```

### Reset seperti Laravel

Kalau kamu mau reset database lalu migrate + seed lagi dalam satu langkah, pakai script ini:

```bash
python scripts/utils/reset_db.py
```

Script tersebut akan:

1. Drop `public schema` beserta semua tabelnya.
2. Jalankan ulang `sql/01_schema.sql`.
3. Jalankan ulang `sql/03_fts.sql`.
4. Jalankan `sql/02_seed.py`.

## 9. Siapkan Data Seed

Letakkan file Excel untuk wisata, kuliner, dan nongkrong di folder `data/` sesuai kebutuhan project.

Catatan: setiap file Excel sekarang dibaca dari semua sheet yang ada, jadi data di `indramayu`, `cirebon`, `majalengka`, dan `kuningan` ikut ter-seed semuanya.

Lalu jalankan seeding:

```bash
python sql/02_seed.py
```

Jika ingin memastikan data masuk dengan benar, jalankan:

```bash
python scripts/utils/check_db.py
```

## 10. Jalankan Aplikasi

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Endpoint penting:

- `http://localhost:8001`
- `http://localhost:8001/docs`
- `http://localhost:8001/redoc`

## 11. Jalankan Test

```bash
pytest tests/ -v
```

Per modul:

```bash
pytest tests/test_auth.py -v
pytest tests/test_wisata.py -v
pytest tests/test_sentiment.py -v
pytest tests/test_chatbot.py -v
pytest tests/test_recommendation.py -v
```

## 12. Alur Kerja AI

### Sentiment

- Pastikan model hasil training ada di `ml/sentiment/`.
- Gunakan notebook training di `scripts/colab/sentiment_training.ipynb`.
- Setelah model siap, implementasi logika prediksi di `app/services/sentiment_service.py`.

### Recommendation

- Pastikan artefak model rekomendasi ada di `ml/recommendation/`.
- Gunakan notebook training di `scripts/colab/recommendation_training.ipynb`.
- Setelah itu, isi `app/services/recommendation_service.py`.

### Chatbot

- Siapkan prompt di `prompts/chatbot_prompts.py`.
- Pastikan koneksi Gemini aktif lewat `GEMINI_API_KEY`.
- Implementasi retrieval dan session management ada di `app/services/chatbot_service.py`.

## 13. Urutan Kerja yang Disarankan

1. Clone repo dan aktifkan virtual environment.
2. Install dependency.
3. Siapkan `.env`.
4. Buat database PostgreSQL.
5. Jalankan schema dan FTS.
6. Kalau mau migration terkelola, setup Alembic.
7. Seed data dari folder `data/`.
8. Verifikasi database.
9. Jalankan server.
10. Isi template service yang masih placeholder.
11. Tambahkan atau jalankan test sesuai fitur yang dikerjakan.

## 14. Catatan Penting

- Folder `ml/` dan `data/` sebaiknya tidak di-commit jika berisi artefak besar atau data privat.
- Untuk production, gunakan migration tool seperti Alembic, bukan auto-create tabel dari startup event.
- Jika struktur seed berubah, pastikan urutan schema, FTS, dan seed tetap konsisten.
- Tabel `wisata`, `kuliner`, dan `nongkrong` sekarang punya `uid` UUID selain `id` internal, jadi identifier publik tidak lagi bergantung pada angka berurutan.
