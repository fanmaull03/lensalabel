# Container dan staging LensaLabel

Checkout `app-hosting-fast` sudah menggabungkan konten `edukasi-content`.
Paket ini memakai satu backend FastAPI, satu frontend Nginx, dan PostgreSQL
persisten di luar Compose. Jalankan pada Linux x86-64 dengan RAM host minimal
8 GiB; backend diberi batas 6 GiB. Mulai dengan satu worker dan satu instance.

## Bangun dan siapkan database

Sediakan Docker Engine dengan Compose. Salin `deploy.env.example` menjadi
`deploy.env`, lalu isi `DATABASE_URL` dan `PUBLIC_ORIGIN`. Gunakan origin HTTPS
persis yang dibuka pengguna. Jangan commit `deploy.env`.

Pada database baru yang kosong, dari root repo jalankan:

```sh
docker compose --env-file deploy.env build
docker compose --env-file deploy.env run --rm --no-deps backend python -m alembic upgrade head
docker compose --env-file deploy.env run --rm --no-deps backend python -m app.db.seed_knowledge_base_deploy --dry-run
docker compose --env-file deploy.env run --rm --no-deps backend python -m app.db.seed_knowledge_base_deploy --apply
docker compose --env-file deploy.env up -d
```

`--apply` hanya untuk database kosong. Pada database berisi data, ambil dan
verifikasi dump sebelum memilih prosedur migrasi yang sesuai. Jangan menjalankan
seed KB v1. Payload deploy memuat 259 bahan dan 1.030 sinonim; `/health`
memeriksa 1.289 varian beserta hash KB dan konfigurasi beku.

## Uji sebelum menerima trafik

`/health` memeriksa database, KB, dan konfigurasi. `/ready` juga memuat model
EasyOCR. Health check container memakai `/ready`, sehingga frontend baru dimulai
setelah model siap. Pemuatan pertama dapat memerlukan lebih dari 30 detik.

```sh
curl -f http://127.0.0.1:8080/ready
python backend/tools/staging_smoke.py --url http://127.0.0.1:8080 --photo /path/to/foto-uji.jpg
```

Gunakan foto uji non-sensitif. Skrip melaporkan waktu HTTP untuk `/health`,
`/ready`, dan satu `/identify` dengan OCR sungguhan. Ulangi di host tujuan;
catat durasi, puncak RAM, dan status HTTP. Jika perlu membandingkan hasil
dengan cache penelitian, pakai `backend/tools/deploy_smoke_test.py` bersama
artefak pembanding yang disimpan terpisah.

Nginx membatasi body foto 11 MiB dan teks 32 KiB, laju permintaan, serta waktu
respons backend 240 detik. API membatasi file 10 MiB, resolusi 20 megapiksel,
dan teks manual 5.000 karakter. Cocokkan timeout pada load balancer di depan
Nginx. Bila reverse proxy membuat semua pengguna terlihat sebagai satu IP,
atur identitas IP klien secara tepercaya pada gateway sebelum akses publik.

Compose mengikat port frontend ke `127.0.0.1` secara default. Pasang HTTPS
di load balancer atau reverse proxy pada host, lalu teruskan ke port 8080.
Backend hanya dapat diakses melalui jaringan Compose. Set `PUBLIC_ORIGIN`
menjadi URL HTTPS tersebut; CORS bukan pengganti pembatasan akses API.

`MATCHER_MODE=frozen` adalah default. Mode `optimized` tersedia dengan bukti
kesetaraan di `docs/deployment/matcher_mode_evidence.md`; uji mode yang akan
dipakai pada host tujuan. Konten edukasi masih menampilkan status tinjauan
ahli gizi.

Versi dependensi langsung dipatok di `backend/requirements-deploy.txt` dan
pasangan Torch/TorchVision CPU mengikuti versi yang diuji lokal. Dependensi
transitif dan digest base image belum dikunci. Image Linux perlu dibangun dan
diuji sebelum rilis; pada audit lokal 26 Oktober 2026, Docker dan WSL tidak
tersedia di mesin pengembangan.
