# 🧪 Panduan Pengujian (Testing) Lengkap — Smart Tourism API

Dokumen ini menjelaskan cara menjalankan server, melakukan testing manual via Swagger, serta menjalankan automated unit testing.

---

## 1. Cara Menjalankan Server

Pastikan virtual environment aktif dan dependencies sudah terinstall.

```powershell
# 1. Aktifkan venv
.\venv\Scripts\activate

# 2. Set environment encoding (khusus Windows agar tidak error emoji/unicode)
$env:PYTHONIOENCODING='utf-8'

# 3. Jalankan server dengan auto-reload
uvicorn app.main:app --reload --port 8000
```
Akses Swagger UI di: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 2. Automated Testing (Unit Testing)

Kami menggunakan `pytest` untuk testing otomatis.

### 2a. Menjalankan SEMUA Test (1 Perintah)
Gunakan perintah ini untuk menjalankan semua test di folder `tests/`:
```powershell
$env:PYTHONPATH="."
venv\Scripts\pytest tests/
```

### 2b. Menjalankan Test Spesifik
*   **Testing Sentimen (Slang & Cleaning)**:
    ```powershell
    venv\Scripts\pytest tests/test_sentiment.py
    ```
*   **Testing Sorting (Rating & Sentimen)**:
    ```powershell
    venv\Scripts\pytest tests/test_sorting.py
    ```

---

## 3. Manual Testing via Swagger (Skenario Utama)

### 3a. Melihat Detail Sentimen per Tempat
1.  Buka `GET /api/v1/wisata/{kode}`.
2.  Cek field `total_positif` dan `total_negatif`.
3.  Frontend dapat menghitung: `(total_positif / total_ulasan_scraped) * 100` untuk persentase.

### 3b. Filtering & Sorting (Dashboard)
Gunakan endpoint `GET /api/v1/wisata/` (atau kuliner/nongkrong) dengan parameter:
*   `sort_by`: pilih `rating` atau `sentimen`.
*   `order`: pilih `desc` (tertinggi) atau `asc` (terendah).
*   `wilayah`: filter daerah tertentu (Indramayu/Cirebon/Majalengka/Kuningan).

**Contoh Skenario:**
*   "Cari wisata di Majalengka dengan sentimen terbaik":
    `GET /api/v1/wisata/?wilayah=Majalengka&sort_by=sentimen&order=desc`
*   "Cari kuliner dengan rating terendah di semua wilayah":
    `GET /api/v1/kuliner/?sort_by=rating&order=asc`

---

## 4. Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `ModuleNotFoundError: No module named 'app'` | Pastikan sudah set `$env:PYTHONPATH="."` sebelum running pytest. |
| `UnicodeEncodeError` | Jalankan `$env:PYTHONIOENCODING='utf-8'` sebelum uvicorn. |
| Data sentimen masih 0 | Pastikan sudah menjalankan `POST /api/v1/sentiment/sync-all` (Admin). |
