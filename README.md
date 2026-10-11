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

Regenerasi anotasi kalibrasi terhadap KB aktif (dari root proyek):

```powershell
backend\.venv\Scripts\python.exe evaluation\generate_calibration_review.py
```

Skrip membaca `evaluation/splits/calibration_set.csv` dan transkripsi manual,
memperbarui `dataset/ground_truth/calibration_ingredients_gt.json` lewat exact
match nama/sinonim, lalu membuat kandidat tambahan lenient pada
`dataset/ground_truth/calibration_review.xlsx`. Lenient menggunakan normalisasi
istilah, toleransi satu edit untuk kata minimal enam karakter, dan maksimal tiga
kata sisipan. Nama umum yang berada di dalam nama bahan lebih spesifik tidak
digandakan pada anotasi exact. Kandidat tetap menunggu keputusan Y/N pada kolom
`keputusan` sebelum menjalankan `evaluation/merge_reviewed_gt.py`.
Snapshot KB disimpan di `evaluation/kb_snapshot.json`, ringkasan perubahan di
`dataset/ground_truth/calibration_regeneration_summary.json`, dan hasil lama
dicadangkan di `evaluation/results/calibration_annotation_backups/`.
Tambahkan `--dry-run` untuk menghitung hasil tanpa menulis ulang artefak.

Untuk memulai review baru berdasarkan KB terbaru dan mengabaikan keputusan v1:

```powershell
backend\.venv\Scripts\python.exe evaluation\generate_calibration_review_v2.py --fresh-review
```

Hasilnya adalah anotasi strict yang diperbarui dan
`dataset/ground_truth/calibration_review_v2.xlsx`, dengan delapan kolom:
`filename`, `standard_name`, `category`, `sumber`, `matched_variant`,
`potongan_teks`, `keputusan`, `status_vs_v1`. Semua kandidat berstatus `BARU`
dengan keputusan kosong pada kolom G. Skrip ini tidak menjalankan merge final.

Review terbaru memakai `generate_calibration_review.py --review-v4` dan
`calibration_review_v4.xlsx`. Kode INS cocok persis; pasangan zat terlarang
dikecualikan dari toleransi typo; longest-match-wins lenient hanya untuk
kelapa/sawit. Relasi taksonomi lainnya ditandai untuk review, tanpa menghapus
kandidat. Semua persetujuan Y v2 dipertahankan. Merge membaca nama kolom dan
menolak keputusan aktif yang belum diisi.
Lihat [hasil v4 dan panduan Colab](docs/evaluation/calibration_v4.md), serta
[notebook grid search](evaluation/notebooks/calibration_grid_search_colab.ipynb).

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

Knowledge base menggunakan 240 entri tetap dari
`Lembar_Validasi_KB_Diet_GFCF_Autisme_final.pdf`: 118 Aman, 80 Perlu Perhatian,
dan 42 Hindari. Data sumber, nomor baris/halaman, sinonim, kode aditif, dan
rujukan R1–R11 disimpan di `backend/app/db/knowledge_base_gfcf.json`.
Kelompok bahan pada satu baris PDF tetap menjadi satu entri database.
Kategori mengikuti kolom Usulan Peneliti; status validasi ahli tidak diaktifkan
karena kolom koreksi dan persetujuan ahli pada dokumen masih kosong.

`python -m app.db.seed_knowledge_base --dry-run` menampilkan rencana perubahan.
Tanpa `--dry-run`, skrip memperbarui bahan dan sinonim, menambahkan entri baru,
serta menghapus/menggabungkan bahan lama di luar daftar tetap dalam satu transaksi.
ID bahan yang masih digunakan dan riwayat validasinya dipertahankan;
perubahan kategori mengembalikan `is_validated=False`.
Cadangan lengkap tiga tabel sebelum perubahan disimpan sebagai JSON di
`evaluation/results/knowledge_base_backups/`. Menjalankan ulang skrip dengan
data yang sudah sesuai tidak mengubah database.
Kode rentang sumber pati tidak diperluas menjadi seluruh nomor dalam rentang;
kode pada krimer campuran dan kode vanilin bertanda “terkait” disimpan sebagai
metadata sumber, tanpa digunakan sebagai alias tunggal bahan tersebut.

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
