# LensaLabel

**Lihat Jelas Komposisi, Pilih dengan Pasti.**

LensaLabel membantu memeriksa keamanan bahan makanan pada label kemasan untuk
kebutuhan diet **Gluten-Free Casein-Free (GFCF)**. Cukup foto (atau ketik)
daftar komposisi, dan LensaLabel membaca teksnya, mencocokkan tiap bahan dengan
basis pengetahuan, lalu memberi status: **Aman**, **Perhatian**, atau **Hindari**
— tanpa perlu menghafal istilah teknis di baliknya.

## Fitur

- **Pindai label** lewat kamera (live) atau unggah foto dari galeri.
- **Ketik manual** — tempel/ketik daftar komposisi bila tidak bisa memotret.
- **OCR** membaca teks komposisi dari foto kemasan.
- **Fuzzy matching** mencocokkan tiap bahan ke basis pengetahuan meski ada salah ketik/ejaan.
- **Klasifikasi per bahan** (Aman / Perhatian / Hindari) + verdict keseluruhan produk.
- **Panel "Teks Terbaca"** menyorot bahan yang perlu dihindari langsung di teks hasil.
- **Modul edukasi GFCF** dan halaman info sistem.

## Tech Stack

| Bagian | Teknologi |
|--------|-----------|
| Backend | FastAPI, SQLAlchemy, PostgreSQL, EasyOCR, OpenCV, RapidFuzz |
| Frontend | React, Vite, Tailwind CSS, React Router |

## Struktur

```
backend/    FastAPI: OCR, preprocessing, fuzzy matching, rule-based classifier
frontend/   React + Vite (mobile-first web app, glassmorphism UI)
dataset/    foto kemasan, ground truth, basis pengetahuan bahan
evaluation/ skrip evaluasi akurasi (CER/WER, Precision/Recall/F1)
docs/       catatan teknis
```

## Prasyarat

- Python 3.12+
- Node.js 18+
- PostgreSQL 14+ (berjalan lokal)

## Menjalankan

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Buat file `backend/.env` (lihat `.env.example`) berisi koneksi database:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/lensalabel
```

Siapkan skema & isi basis pengetahuan, lalu jalankan server:

```bash
alembic upgrade head
python -m app.db.seed_knowledge_base
uvicorn app.main:app --reload
```

Backend jalan di `http://127.0.0.1:8000` (dokumentasi API: `/docs`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Arahkan frontend ke backend lewat `frontend/.env.development`:

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Frontend jalan di `http://localhost:5173`.

## API

| Method | Endpoint | Keterangan |
|--------|----------|------------|
| `POST` | `/identify` | Upload foto kemasan (multipart), kembalikan verdict + bahan per kategori. |
| `POST` | `/identify-manual` | Kirim `{"text": "..."}` daftar komposisi, hasil sama seperti `/identify`. |
| `GET`  | `/health` | Cek status backend & koneksi database. |

## Catatan

- OCR berjalan di CPU dan bisa memakan **30 detik – 2 menit** per foto pada
  perangkat kelas menengah — ini normal, bukan hang.
- Kamera live memerlukan **secure context**: `localhost` aman, tetapi akses
  lewat IP jaringan (`http://192.168.x.x`) diblokir browser. Gunakan HTTPS atau
  fitur unggah galeri saat menguji dari perangkat lain.
- LensaLabel adalah alat bantu informasi, **bukan** pengganti saran dokter atau
  ahli gizi.
