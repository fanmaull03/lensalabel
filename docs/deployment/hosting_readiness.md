# Kesiapan hosting LensaLabel

Diperbarui 16 Oktober 2026. Ini rancangan image, bukan image yang sudah dibangun atau layanan yang sudah di-deploy. Konfigurasi penelitian dan hasil evaluasi tidak diubah.

## Kapasitas dan pilihan hosting

Profil CPU lokal pada tiga foto kalibrasi (i3-1005G1, 7,74 GiB RAM, EasyOCR 1.7.2, Torch 2.13.0 CPU, OpenCV headless 5.0.0.93) mencatat pemuatan model 13,70 detik, proses hangat rata-rata 40,02 detik per foto, dan RSS puncak tersampel 2.456 MiB. Komponen waktu rata-rata: dekode 0,254, preprocessing 0,072, OCR 36,955, ekstraksi dan tokenisasi 0,004, pemuatan KB 0,275, matcher 2,461 detik; klasifikasi kurang dari 0,001 detik. Timer memakai QueryUnbiasedInterruptTime; RAM sedang terbatas saat profil, sehingga uji Linux tetap wajib. Profil matcher tersebut memakai eksperimen lokal, bukan jaminan waktu tag beku. Perkiraan image Linux CPU 1,3–2,5 GiB termasuk bobot EasyOCR sekitar 94 MiB; ukuran riil belum diukur.

Mulai uji pada **RAM 4 GiB minimum**, lebih aman 6–8 GiB, satu worker dan satu OCR serentak. Batasi concurrency platform menjadi satu dan ukur ulang cold start, latensi p95, serta RSS pada image Linux. [Cloud Run](https://docs.cloud.google.com/run/quotas) mendokumentasikan memori sampai 32 GiB dan timeout permintaan sampai 60 menit; kelas 4–8 GiB memenuhi batas sumber daya. [Render compute plans](https://render.com/docs/compute-plans) menyediakan kelas 4/8 GiB; [dokumentasi Render](https://render.com/docs/heroku) menyebut respons HTTP hingga 100 menit. Keduanya layak diuji; ini belum keputusan pembelian. [Heroku](https://devcenter.heroku.com/articles/http-routing) memerlukan respons awal dalam 30 detik, sehingga alur sinkron CPU lokal sekitar 40 detik tidak cocok tanpa pola job/polling. Batas Railway belum cukup terverifikasi untuk direkomendasikan. Batas sumber daya dan harga perlu dicek lagi saat deployment.

## Rancangan image tersaring

Gunakan `backend/` sebagai build context dengan `.dockerignore` allowlist di bawah, sehingga dataset, GT, paket wawancara, dump, dan `.env` tidak dikirim ke builder. Hanya kode backend, migrasi, KB v2 operasional `app/db/knowledge_base_v2_deploy.json`, dan salinan konfigurasi beku di `backend/deploy/` yang masuk image. Jangan memasukkan draf validasi ahli atau arsip riset. Salinan konfigurasi memiliki SHA-256 sama dengan `evaluation/config_frozen.json`: `6f04865dd02fe7122a93ad6c6a0b32223f059205758bfb1b793477fe7426dd80`. Loader aplikasi memverifikasi sidecar saat startup.

Contoh `.dockerignore` untuk context `backend/` (rancangan, belum dibuat):

```dockerignore
*
!app/
!app/**
!alembic/
!alembic/**
!alembic.ini
!requirements.txt
!deploy/
!deploy/config_frozen.json
!deploy/config_frozen.sha256
**/.env*
**/__pycache__/
**/*.pyc
app/db/knowledge_base_gfcf.json
```

Rancangan `backend/Dockerfile` berikut belum dijalankan. Sebelum build, kunci pasangan wheel CPU Torch/TorchVision dan seluruh paket pada lockfile Linux; `backend/requirements.txt` sekarang belum dipatok. Jangan menyalin `.env`, berkas riset, foto, atau dump. Unduh bobot EasyOCR saat build sehingga startup tidak mengunduh dari jaringan.

```dockerfile
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EASYOCR_GPU=0 \
    EASYOCR_MODULE_PATH=/opt/easyocr \
    LENSALABEL_FROZEN_CONFIG=/app/backend/deploy/config_frozen.json
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY requirements.txt ./requirements.txt
# Ganti dengan pasangan Torch/TorchVision CPU yang dipatok dan teruji di Linux.
RUN python -m pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY deploy/ ./deploy/
RUN python -c "import easyocr; easyocr.Reader(['id', 'en'], gpu=False)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

`DATABASE_URL` harus diberikan oleh secret manager hosting, tanpa `.env` di image. `LENSALABEL_CORS_ORIGINS` harus berisi origin frontend yang tepat, dipisahkan koma; default `*` hanya untuk pengembangan lokal. Endpoint `/identify` membatasi unggahan 10 MiB, menutup file sementara dalam `finally` baik berhasil maupun gagal, dan semaphore membatasi OCR satu per satu dalam satu proses. Samakan batas unggahan dan timeout pada proxy. `/health` wajib dipakai sebagai health check: mengembalikan HTTP 503 bila database/KB tidak sehat, termasuk versi KB, hash KB, dan hash konfigurasi.

## Database hosting baru

1. Set `DATABASE_URL` sebagai secret ke PostgreSQL baru dan pastikan host yang dituju benar. Jangan jalankan seed v1.
2. Jalankan `python -m alembic -c alembic.ini upgrade head` dari `/app/backend`; cek revision `c71f3d95a620`.
3. Jalankan `python -m app.db.seed_knowledge_base_deploy --dry-run`, lalu `--apply` satu kali pada database kosong. Seed ini memakai KB v2 operasional yang terlacak dan menolak tabel bahan yang sudah terisi. Tabel `expert_validations` tetap kosong pada paket deploy yang disanitasi.
4. Verifikasi SQL: 259 baris `ingredients`, 1.030 `ingredient_synonyms`, 1.289 varian total. Periksa `GET /health`: `status=ok`, `kb_version=v2`, `kb_hash=4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e`, dan `config_hash=6f04865dd02fe7122a93ad6c6a0b32223f059205758bfb1b793477fe7426dd80`. Alihkan trafik hanya jika semua cocok.
5. Pada database yang sudah berisi data, ambil dan verifikasi `pg_dump` sebelum migrasi. Seed deploy ini hanya untuk database kosong; gunakan prosedur migrasi yang telah diaudit untuk DB berisi data.

## Usulan job dan polling, belum diimplementasikan

CPU lokal rata-rata sekitar 40 detik per foto, sementara sebagian gateway membatasi respons sinkron. Rancangan paling kecil: `POST /identify-jobs` menerima foto, mengembalikan HTTP 202 serta ID acak; `GET /identify-jobs/{id}` mengembalikan `queued`, `running`, `succeeded`, atau `failed` dan hasil yang sama dengan `/identify`. Satu worker menjalankan pipeline beku, penyimpanan sementara privat memiliki TTL, dan berkas foto dihapus segera setelah selesai atau gagal. Polling frontend berhenti pada status terminal atau timeout. Perkiraan pekerjaan: satu model job, dua endpoint, penyimpanan/TTL, polling UI, idempotensi/limit antrean, dan tes sekitar 2–4 hari pengembangan plus uji beban; angka ini estimasi, bukan komitmen jadwal. Tes baru perlu mencakup status transisi, error, penghapusan foto, batas antrean, timeout, dan kesetaraan keluaran sinkron. Matcher, KB, threshold, dan evaluasi tidak perlu diubah.

Urutan deploy: tetapkan lockfile CPU dan image tersaring; bangun image dengan bobot; set secret database dan CORS; migrasi; seed KB v2; cek hitungan dan `/health`; uji satu foto non-evaluasi pada staging; ukur RAM/waktu di host; baru alihkan frontend dan aktifkan monitoring serta backup. Rancangan image belum dibangun atau dijalankan.
