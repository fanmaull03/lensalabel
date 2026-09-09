— tanpa perlu menghafal istilah teknis di baliknya.
# LensaLabel

Implementasi tugas akhir: OCR + Rule-Based Fuzzy String Matching untuk
identifikasi keamanan bahan makanan pada produk kemasan, ditujukan untuk
mendukung penerapan diet Gluten-Free Casein-Free (GFCF) bagi anak dengan
Autism Spectrum Disorder (ASD).

Project ini menggabungkan image preprocessing, EasyOCR, tokenisasi berbasis
regex, pencocokan fuzzy (RapidFuzz) dan classifier berbasis aturan untuk
menghasilkan status per-bahan (`aman` / `perhatian` / `hindari`) dan verdict
produk. Knowledge base bahan disusun menurut literatur GFCF dan divalidasi oleh
ahli gizi.

## Ringkasan

- Fokus akademik: integrasi OCR + Rule-Based Fuzzy Matching untuk menangani
  variasi ejaan dan kesalahan ekstraksi OCR pada teks komposisi.
- Dataset uji: 200 foto kemasan (100 datar/fleksibel + 100 silindris/melengkung)
  dengan transkripsi ground-truth manual.
- Knowledge base: daftar bahan + sinonim + kategori keamanan (Aman/Perhatian/Hindari),
  divalidasi oleh tenaga ahli.

## Arsitektur & alur

1. Upload foto atau input teks manual
2. Image preprocessing (grayscale, noise reduction, CLAHE, deskewing)
3. OCR (EasyOCR singleton, downscale ke lebar maksimum untuk performa)
4. Ekstraksi bagian komposisi + tokenisasi regex
5. Fuzzy matching per-token terhadap knowledge base (Levenshtein, Jaro-Winkler,
   character n-gram → skor komposit)
6. Rule-based classification → verdict produk (aturan kehati-hatian: ``hindari`` > ``perhatian`` > ``aman``; ada status `perlu_verifikasi` dan `tidak_terbaca`)

Komponen utama ada di `backend/app`:
- OCR: `app/ocr/reader.py`
- Preprocessing: `app/preprocessing/pipeline.py`
- Tokenizer: `app/tokenizer/tokenizer.py`
- Matching: `app/matching/fuzzy_matcher.py`
- Classifier: `app/classifier/rule_based.py`
- API routes: `app/api/routes_identify.py`

## Evaluasi

- OCR: Character Error Rate (CER) dan Word Error Rate (WER).
- Identifikasi & klasifikasi: Precision, Recall, F1-Score.
- Kalibrasi threshold pencocokan dilakukan pada subset kalibrasi (40 sampel),
  lalu diuji pada subset evaluasi akhir (160 sampel).

## Teknologi

- Backend: FastAPI, SQLAlchemy, PostgreSQL, EasyOCR, OpenCV, RapidFuzz.
- Frontend: React + Vite + Tailwind CSS.
- See `backend/requirements.txt` for Python deps.

## Prasyarat & jalankan singkat

1. Backend (Windows example):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Buat `backend/.env` (lihat `.env.example`) dengan `DATABASE_URL` ke Postgres.

3. Migrasi dan seed knowledge base:

```powershell
alembic upgrade head
python -m app.db.seed_knowledge_base
uvicorn app.main:app --reload
```

API interaktif: `http://127.0.0.1:8000/docs`.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Pastikan `frontend/.env.development` mengarah ke `VITE_API_BASE_URL=http://127.0.0.1:8000`.

## Catatan penting

- OCR pada CPU dapat memakan waktu (30s–2min per foto pada perangkat
  menengah). Downscaling dan preprocessing dipakai untuk menyeimbangkan akurasi
  dan waktu eksekusi.
- Threshold dan bobot skor komposit di `app/matching/fuzzy_matcher.py` perlu
  kalibrasi empiris; konfigurasi awal ada di file tersebut.
- Knowledge base harus diisi dan disahkan (seed script) sebelum API `/identify`
  berguna, karena sistem akan mengembalikan error jika KB kosong.

## Referensi

Dokumen metode, dataset sampling, dan rencana evaluasi berasal dari proposal
skripsi: "Implementasi Optical Character Recognition dan Rule-Based Fuzzy
String Matching untuk Identifikasi Keamanan Bahan Makanan bagi Anak Autisme"
(2026).

---
Untuk detail implementasi lihat kode pada folder `backend/app` dan dokumentasi
API di endpoint `/docs` saat server berjalan. Jika mau, saya bisa bantu membuat
ringkasan pipeline visual atau menyiapkan skrip evaluasi otomatis.
