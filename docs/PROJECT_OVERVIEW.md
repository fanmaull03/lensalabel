# Dokumentasi Proyek: LensaLabel

> Implementasi Optical Character Recognition (OCR) dan Rule-Based Fuzzy String
> Matching untuk Identifikasi Keamanan Bahan Makanan bagi Anak Autisme.

## 1. Tentang Proyek

LensaLabel adalah sistem tugas akhir (skripsi) yang membantu orang tua/pendamping
anak dengan Autism Spectrum Disorder (ASD) memeriksa keamanan bahan pada produk
makanan kemasan untuk diet **Gluten-Free Casein-Free (GFCF)** — tanpa perlu
menghafal istilah teknis bahan.

Pengguna cukup memotret label komposisi (atau mengetik teksnya). Sistem membaca
teks komposisi lewat OCR, mencocokkan tiap bahan ke knowledge base, lalu
menyimpulkan status produk:

| Status | Arti |
|---|---|
| `aman` | Semua bahan teridentifikasi aman untuk diet GFCF |
| `perhatian` | Ada bahan yang perlu diwaspadai |
| `hindari` | Ada bahan yang harus dihindari (mengandung gluten/kasein) |
| `perlu_verifikasi` | Ada bahan yang tidak ditemukan di knowledge base |
| `tidak_terbaca` | Teks komposisi gagal diekstrak dari foto |

## 2. Masalah yang Diselesaikan

Teks komposisi pada kemasan sulit diproses karena:

- **Variasi ejaan** — satu bahan punya banyak nama (mis. "susu bubuk",
  "milk powder", "susu skim").
- **Kesalahan OCR** — karakter salah baca (`0`↔`O`, `1`↔`l`), terutama pada
  kemasan melengkung, reflektif, atau cetakan kecil.
- **Istilah teknis** — kode aditif (INS), nama kimia, dan istilah asing yang
  tidak dikenal pengguna awam.

Pencocokan exact-match tidak cukup, sehingga dipakai **fuzzy string matching**
dengan aturan klasifikasi (rule-based).

## 3. Cara Kerja (Pipeline)

```
Foto label ──► Preprocessing ──► OCR ──► Tokenisasi ──► Fuzzy Matching ──► Klasifikasi ──► Verdict
              (grayscale,        (EasyOCR)  (regex,      (RapidFuzz,         (rule-based)      per produk
               denoise, CLAHE,              ekstraksi     skor komposit)
               deskew)                      komposisi)
```

Tahapan dan lokasi kode (`backend/app/`):

1. **Upload / input teks** — `api/routes_identify.py`
2. **Preprocessing citra** — `preprocessing/pipeline.py`
   (grayscale, noise reduction, CLAHE, deskewing, downscale lebar maksimum)
3. **OCR** — `ocr/reader.py` (EasyOCR, dijalankan sebagai singleton)
4. **Ekstraksi & tokenisasi komposisi** — `tokenizer/tokenizer.py` (berbasis regex)
5. **Fuzzy matching** — `matching/fuzzy_matcher.py`
   (gabungan Levenshtein, Jaro-Winkler, character n-gram → skor komposit
   dengan threshold terkalibrasi)
6. **Klasifikasi rule-based** — `classifier/rule_based.py`
   (aturan kehati-hatian: `hindari` > `perhatian` > `aman`)

## 4. Knowledge Base (KB)

- **240 entri tetap** dari dokumen `Lembar_Validasi_KB_Diet_GFCF_Autisme_final.pdf`:
  - 118 **Aman**, 80 **Perlu Perhatian**, 42 **Hindari**
- Tiap entri memuat nama standar, sinonim, kode aditif (INS), kategori keamanan,
  rujukan literatur (R1–R11), dan nomor baris/halaman sumber.
- Data sumber: `backend/app/db/knowledge_base_gfcf.json`
- Disusun menurut literatur GFCF dan divalidasi ahli gizi.
- Diisi ke database lewat `python -m app.db.seed_knowledge_base`
  (mendukung `--dry-run`; backup otomatis ke
  `evaluation/results/knowledge_base_backups/`).

## 5. Dataset

- **200 foto kemasan** produk makanan:
  - 100 kemasan datar/fleksibel
  - 100 kemasan silindris/melengkung (kasus sulit untuk OCR)
- Transkripsi ground-truth manual per foto.
- Pembagian data:
  - **Subset kalibrasi (40 sampel)** — untuk menentukan threshold matching.
  - **Subset evaluasi akhir (160 sampel)** — pengujian akhir, terpisah dari kalibrasi.
- Lokasi: `dataset/` (foto mentah, manifest, ground truth) dan `evaluation/splits/`.

## 6. Evaluasi

Metrik yang dipakai:

- **OCR**: Character Error Rate (CER) dan Word Error Rate (WER).
- **Identifikasi & klasifikasi bahan**: Precision, Recall, F1-Score.

Skrip dan artefak evaluasi ada di folder `evaluation/`, meliputi:

- Grid search & kalibrasi threshold (`run_calibration_grid_v2.py`, dsb.)
- Evaluasi 160 sampel (`evaluate_160_metrics.py`, `run_evaluate_160_parallel.py`)
- Ablasi OCR dan analisis fallback (`colab_calibration_ocr_ablation.py`,
  `analyze_evaluation_fallback.py`)
- Audit knowledge base v2 (`audit_kb_v2_*.py`)
- Notebook Colab: `evaluation/notebooks/`, runbook di `evaluation/COLAB_*.md`
- Konfigurasi evaluasi dibekukan (`config_frozen.json` + hash SHA-256) untuk
  reproduksibilitas.

Lihat juga `docs/evaluation/` untuk panduan detail.

## 7. Teknologi

| Lapisan | Teknologi |
|---|---|
| Backend | FastAPI, SQLAlchemy, Alembic, PostgreSQL |
| OCR & citra | EasyOCR, OpenCV |
| Matching | RapidFuzz |
| Frontend | React, Vite, Tailwind CSS |
| Evaluasi | Python (pandas, dsb.), Google Colab |

## 8. Struktur Repositori

```
lensalabel/
├── backend/          # API FastAPI, pipeline OCR→matching→klasifikasi, DB & seed KB
├── frontend/         # Aplikasi web React + Vite + Tailwind
├── dataset/          # Foto, manifest, ground truth
├── evaluation/       # Skrip evaluasi, kalibrasi, audit KB, hasil, notebook
├── docs/             # Dokumentasi (setup dev, deployment, evaluasi, KB, proposal)
├── proposals/        # Patch usulan perbaikan matcher
└── archive/          # Arsip eksperimen lama
```

## 9. Menjalankan Proyek (Ringkas)

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed_knowledge_base
uvicorn app.main:app --reload
# API docs: http://127.0.0.1:8000/docs
```

```powershell
# Frontend
cd frontend
npm install
npm run dev
```

Prasyarat: `backend/.env` berisi `DATABASE_URL` ke PostgreSQL, dan
`frontend/.env.development` berisi `VITE_API_BASE_URL=http://127.0.0.1:8000`.
Detail lengkap: `docs/DEV_SETUP.md`.

## 10. Catatan Penting

- OCR di CPU lambat (±30 detik–2 menit per foto di perangkat menengah).
- Knowledge base wajib di-seed sebelum endpoint `/identify` dapat dipakai
  (API mengembalikan error jika KB kosong).
- Threshold/bobot matcher di `matching/fuzzy_matcher.py` adalah hasil kalibrasi
  empiris pada subset kalibrasi — jangan diubah tanpa menjalankan ulang
  prosedur kalibrasi.

---

*Dokumen ini adalah ringkasan "tentang apa" proyek. Untuk instruksi operasional
lengkap (setup, seed KB, regenerasi anotasi kalibrasi), lihat `README.md` di root
repositori.*
