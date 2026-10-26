# Deploy LensaLabel

Panduan container dan pemeriksaan staging ada di `DEPLOY_CONTAINER.md`.

Repo ini hanya berisi kode aplikasi dan KB operasional. Transkrip, foto penelitian,
catatan validasi ahli, paket wawancara, hasil evaluasi, dan `.env` disimpan terpisah.

## Backend

Sediakan PostgreSQL dan tetapkan `DATABASE_URL` sebagai variabel lingkungan pada
platform hosting. Jangan menulis kredensial di Git. Dari folder `backend/`:

```powershell
python -m pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed_knowledge_base_v2 --dry-run
python -m app.db.seed_knowledge_base_v2 --apply
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Jalankan `--apply` hanya sekali pada database kosong. Berkas
`backend/app/db/knowledge_base_v2_deploy.json` berisi 259 bahan, kategori, dan
1.030 sinonim yang diperlukan pencocokan. Catatan validasi ahli tidak disertakan
pada database deploy. Matcher membaca tabel `ingredients` dan
`ingredient_synonyms`.

## Frontend

Tetapkan `VITE_API_BASE_URL` pada konfigurasi platform build dengan URL backend
publik, lalu jalankan `npm ci` dan `npm run build` dari folder `frontend/`.
Hasil build berada di `frontend/dist/`.
