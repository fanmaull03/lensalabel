# Kesiapan hosting LensaLabel

Audit 15 Oktober 2026. Dokumen ini adalah rancangan deployment, bukan perubahan pada pipeline penelitian. Database lokal sudah memakai KB v2: 259 bahan, 1.030 sinonim, 264 validasi, dan 1.289 varian matcher; hash kanonik varian database sama dengan sumber evaluasi (`4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e`). Foto evaluasi, GT, dan metrik penelitian tidak diproses ulang.

## Pengukuran CPU lokal

Tiga foto dipilih hanya dari split kalibrasi berdasarkan panjang teks pada cache OCR 1500/OFF: pendek `melengkung_076.jpeg`, median `datar_095.jpeg`, dan panjang `datar_015.jpeg`. Foto tersebut dibaca dan di-OCR ulang sekali untuk profil hosting; keluaran OCR dan prediksi tidak disimpan dan tidak dinilai terhadap GT. Alur yang diukur: baca/dekode, `preprocess`, `extract_text(..., max_width=1500)`, ekstraksi komposisi, tokenisasi, `load_knowledge_base` dari PostgreSQL, `match_token_many`, dan `classify_product`. EasyOCR CPU dimuat sekali sebelum tiga permintaan. Timer memakai Windows `QueryUnbiasedInterruptTime`; sampel RSS proses diambil setiap 25 ms. Karena itu lonjakan yang lebih singkat dari 25 ms bisa terlewat.

Perangkat: laptop Intel Core i3-1005G1, 4 CPU logis, RAM 7,74 GiB, Windows 11; Python 3.12.6, EasyOCR 1.7.2, Torch 2.13.0 CPU, OpenCV headless 5.0.0.93 (`cv2` 5.0.0). Memori tersedia saat mulai hanya 0,79 GiB, sehingga waktu bisa terpengaruh paging dan tidak mewakili server Linux. Pemuatan model pertama memerlukan **13,703 detik** dan mencapai RSS 855,5 MiB.

| Foto | Baca + dekode | Pra-pemrosesan | OCR | Ekstraksi + tokenisasi | Muat KB | Matcher | Klasifikasi | Total hangat | Puncak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| melengkung_076 | 0,372 dtk | 0,081 | 36,695 | <0,001 | 0,678 | 2,541 | <0,001 | 40,367 | 2.227 MiB |
| datar_095 | 0,202 | 0,070 | 38,301 | 0,003 | 0,090 | 1,085 | <0,001 | 39,751 | 2.456 MiB |
| datar_015 | 0,187 | 0,065 | 35,869 | 0,008 | 0,056 | 3,756 | <0,001 | 39,941 | 2.442 MiB |
| Rata-rata | 0,254 | 0,072 | 36,955 | 0,004 | 0,275 | 2,461 | <0,001 | **40,020** | puncak sampel **2.456 MiB** |

Permintaan pertama setelah proses baru sekitar 54 detik jika 13,703 detik pemuatan model ditambahkan ke 40,367 detik pemrosesan foto pertama. Ini bukan pengukuran HTTP/proxy, hanya alur Python dalam satu proses. Matcher yang aktif di working tree saat profil memiliki optimasi lokal yang belum dikomit; angka matcher ini **bukan** jaminan waktu matcher pada tag evaluasi beku. Catatan enam teks sebelum optimasi menunjukkan matcher serial 12–130 detik pada beberapa kasus; ukur ulang pada image deployment sebelum menetapkan SLA.

**Perbedaan konfigurasi runtime:** `evaluation/config_frozen.json` mencatat MAX_OCR_WIDTH 1500 dan adaptive threshold OFF, tetapi `/identify` memanggil `extract_text(preprocess(image))` tanpa argumen lebar; default `backend/app/ocr/reader.py` adalah **2000**. Profil di atas memanggil 1500 secara eksplisit. Endpoint lokal yang berjalan sekarang belum dapat disebut memakai konfigurasi OCR beku. Ini perlu keputusan implementasi dan verifikasi tersendiri sebelum demo/hosting; jangan menafsirkan profil 1500 sebagai waktu aktual endpoint 2000. Adaptive threshold tidak dipakai pada alur yang diukur.

## Memori, disk, dan rancangan image

RSS puncak satu proses adalah 2,46 GiB. Dengan ruang untuk variasi citra, allocator Torch, OS, dan proxy, kelas **minimal 4 GiB RAM untuk satu permintaan serentak** layak diuji; 6–8 GiB lebih aman untuk pilot, tetapi tetap perlu profil pada Linux dan foto terburuk. Batasi concurrency OCR menjadi satu per proses sampai pengukuran beban paralel tersedia. Menggandakan worker juga menggandakan model dan mendekati penggandaan RAM. EasyOCR reader dibuat singleton secara lazy; cold start menambah sekitar 14 detik pada laptop.

Instalasi lokal Windows memakai sekitar 1.102 MiB `site-packages`, dengan `torch` 489 MiB, `torchvision` 14 MiB, `easyocr` 15 MiB, dan `cv2` 112 MiB. Dua bobot EasyOCR yang terpasang (`craft_mlt_25k.pth` dan `latin_g2.pth`) berjumlah sekitar 94 MiB. Estimasi awal image Linux CPU **1,3–2,5 GiB** setelah base image, library sistem, dan layer; ini bukan ukuran image hasil build. Gunakan wheel Torch **CPU-only**, pin versi Torch/TorchVision yang kompatibel dengan EasyOCR, `--no-cache-dir`, dan jangan memasukkan dataset, dump DB, `.env`, atau paket wawancara. `backend/requirements.txt` kini belum mematok versi; lockfile deployment perlu ditetapkan sebelum build yang dapat direproduksi.

Rancangan Dockerfile berikut **belum dibuat atau dijalankan**. Baris instalasi Torch perlu dikunci ke pasangan wheel CPU yang tersedia pada saat build; image harus dibangun hanya dari konteks yang telah disaring dengan `.dockerignore` agar berkas sensitif tidak ikut dikirim ke builder.

```dockerfile
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EASYOCR_GPU=0 \
    EASYOCR_MODULE_PATH=/opt/easyocr
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# Pin torch + torchvision CPU-only yang kompatibel sebelum image ini dibangun.
RUN python -m pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY evaluation/results/kb_v2_phase2/kb_v2_review.json evaluation/results/kb_v2_phase2/kb_v2_review.json
COPY evaluation/config_frozen.json evaluation/config_frozen.json
COPY archive/kb_v1_and_gt_before_expert/knowledge_base_gfcf.json archive/kb_v1_and_gt_before_expert/knowledge_base_gfcf.json
RUN python -c "import easyocr; easyocr.Reader(['id', 'en'], gpu=False)"
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

Seed v2 masih membaca **dua** JSON: KB v2 dan arsip khusus KB v1 untuk metadata rujukan. Karena itu Dockerfile menyalin satu berkas arsip KB tersebut secara eksplisit, bukan seluruh `archive/`. Migrasi/seed jangan diletakkan di `CMD` setiap replika: jalankan sebagai release job tunggal setelah dump database hosting dan sebelum mengalihkan trafik. Bobot EasyOCR dibangun ke image agar startup tidak bergantung pada unduhan model. Rancangan belum mencakup frontend statis, TLS, atau `.dockerignore` aktual.

## Konfigurasi, unggahan, dan waktu respons

| Bagian | Kondisi kode sekarang | Kebutuhan hosting |
|---|---|---|
| Database | `DATABASE_URL` dari environment atau `backend/.env`; default di kode hanya contoh lokal. | Set URL PostgreSQL hosting sebagai secret environment, dengan TLS sesuai penyedia. Jangan membangun `.env` ke image. |
| OCR | `EASYOCR_GPU` default `0`; `PORT` dibaca pada contoh perintah container. | CPU-only kecuali ada host GPU yang diuji. Siapkan bobot model saat build. |
| Frontend | `VITE_API_BASE_URL` digunakan saat build Vite. | Arahkan ke origin API hosting atau pakai reverse proxy satu origin. Ini bukan secret. |
| CORS | `allow_origins=["*"]`, semua metode dan header. | Batasi ke origin frontend resmi sebelum publik; perubahan kode terpisah dari audit ini. |
| Unggahan | `/identify` membatasi berkas 10 MiB, membaca paling banyak 10 MiB + 1 byte. | Samakan limit di proxy; batasi jenis/ukuran dimensi citra sebelum decode untuk melindungi RAM. |
| Foto pengguna | Route memproses bytes di memori/objek upload; tidak menyimpan foto secara eksplisit ke database/disk proyek. | Tutup/bersihkan file upload sementara setelah proses, jangan log foto atau OCR mentah, dan hapus payload job setelah TTL bila memakai antrean. |
| Timeout | `fetch` frontend tidak memasang deadline; API sinkron dan tidak punya antrean. | Atur timeout proxy/server berdasar puncak nyata, tampilkan status berjalan; untuk latensi panjang gunakan job asinkron. |

Untuk pola asinkron, usulan antarmuka adalah `POST /identify-jobs` yang mengembalikan ID dan HTTP 202, worker tunggal membaca foto serta menjalankan pipeline yang sama, lalu `GET /identify-jobs/{id}` untuk polling status/hasil. Simpan foto sementara secara privat dengan TTL dan hapus segera setelah selesai/gagal; batasi ukuran antrean dan sediakan timeout job serta pembatalan. Ini rancangan saja; tidak ada endpoint atau penyimpanan job yang dibuat.

## Database hosting dan pembuktian KB

1. Set `DATABASE_URL` hosting sebagai secret dan jalankan perintah dari direktori `/app/backend` agar konfigurasi tidak jatuh ke URL contoh. Pastikan database tujuan benar.
2. Buat `pg_dump --format=custom` penuh dan uji `pg_restore --list` sebelum perubahan.
3. Jalankan `python -m alembic upgrade head`; pastikan `alembic current` menunjukkan `c71f3d95a620`.
4. Jalankan `python -m app.db.seed_knowledge_base_v2 --apply` **sekali**. Jangan menjalankan `seed_knowledge_base.py` lama karena akan mengembalikan 240 entri.
5. Verifikasi 259 `ingredients`, 1.030 `ingredient_synonyms`, 264 `expert_validations`, 1.289 varian. Cocokkan hash berkas JSON dengan `kb_sha256` di config beku (`6e6489bdffe80cc4032dcf82ed9b396a0e00912d516a8353996aff250e3527f8`) lalu cocokkan daftar kanonik `(ingredient_id, standard_name, category, name_variant)` dari `load_knowledge_base()` dengan flatten KB v2. Contoh perintah verifikasi baca-saja tersedia di `docs/DEV_SETUP.md`. Hash kanonik yang diharapkan pada versi ini adalah `4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e`.
6. Baru alihkan trafik setelah `/health` dan pemeriksaan KB lulus. Simpan dump di lokasi privat di luar image/repo.

## Perbandingan kelas hosting

Angka berikut dicek pada dokumentasi resmi 15 Oktober 2026; paket, kuota regional, dan kebijakan jaringan perlu dicek kembali saat memilih paket. Ini perbandingan kelayakan sumber daya, bukan keputusan membeli layanan.

| Alternatif | Batas relevan yang terdokumentasi | Implikasi untuk LensaLabel |
|---|---|---|
| Container terkelola dengan RAM/timeout dapat diatur (contoh Cloud Run) | Hingga 32 GiB per instance dan hingga 60 menit per request; startup instance dibatasi 4 menit menurut [kuota Cloud Run](https://docs.cloud.google.com/run/quotas). | Kelas 4–8 GiB dan concurrency 1 dapat diuji; cold start dan CPU OCR perlu diprofilkan pada image Linux. |
| Web service berbayar dengan worker (contoh Render) | Daftar [compute plan](https://render.com/docs/blueprint-spec) memuat 4 GiB dan 8 GiB; [dokumentasi Render](https://render.com/docs/render-vs-vercel-comparison) menyebut respons HTTP hingga 100 menit. Paket 512 MiB terlalu kecil untuk puncak terukur. | Layak diuji pada paket RAM memadai; worker/job lebih tahan terhadap restart ketimbang request sinkron panjang. |
| Platform container berbasis penggunaan (contoh Railway) | [Dokumentasi paket](https://docs.railway.com/pricing/plans) menunjukkan Free 0,5 GiB dan Trial 1 GiB, keduanya di bawah RSS puncak; paket lebih tinggi menyediakan kapasitas lebih besar. Batas timeout HTTP spesifik belum ditemukan pada halaman resmi yang diperiksa. | Jangan memilih tier kecil. Verifikasi batas timeout/proxy pada paket dan wilayah yang dipakai sebelum request sinkron. |
| PaaS dengan router 30 detik awal (contoh Heroku) | [Dokumentasi router](https://devcenter.heroku.com/articles/http-routing) menetapkan respons awal dalam 30 detik. | Tiga permintaan hangat terukur sekitar 40 detik; pola sinkron saat ini tidak cocok tanpa job/polling atau perubahan protokol respons. |
| VM/container sendiri | RAM dan timeout bergantung VM, reverse proxy, dan proses aplikasi yang disetel sendiri. | Kontrol penuh, tetapi keamanan, patching, TLS, monitoring, backup, dan kegagalan proses menjadi tanggung jawab pengelola. |

## Optimasi matcher yang belum menjadi runtime beku

Working tree saat audit berada pada branch `expert-interview-packet`; `backend/app/matching/fuzzy_matcher.py` **modified dan belum dikomit** (49 baris ditambah, 13 dihapus). `docs/evaluation/timing_summary.md` juga modified; `docs/evaluation/perf_matcher.md` dan `evaluation/benchmark_perf_matcher_200.py` belum dilacak, bersama skrip profil lain. Nama cabang `perf-matcher` ada, tetapi pointer cabang itu sendiri masih di commit `b2b8078`; status file aktif tidak boleh disimpulkan dari nama cabang. Perubahan ini tidak digabung ke `main` atau tag evaluasi dan tidak disentuh dalam audit hosting.

Rancangan optimasi yang menjaga hasil: cache lebar jendela/varian dan string window, saring kandidat hanya dengan batas atas skor yang **terbukti** lebih rendah dari threshold (misalnya batas atas penalti panjang), gunakan `score_cutoff` RapidFuzz hanya jika batasnya konservatif terhadap skor komposit dan urutan tie, lalu pertimbangkan `process.cdist` atau indeks panjang/huruf awal setelah dibuktikan tidak menghapus kandidat typo sah. Indeks huruf awal murni berisiko membuang typo pada huruf awal; jangan dipakai tanpa fallback. Pertahankan urutan kandidat, tie-break, negasi, shared-head, dan span sekunder. Tolok ukur penerimaan: jalankan matcher lama dan kandidat pada **40 cache teks OCR kalibrasi + 160 cache teks OCR evaluasi** tanpa OCR ulang; bandingkan himpunan `(ingredient_id, standard_name, category)` dan verdict **200/200 identik**, lalu ukur waktu dan RAM pada proses bersih. Eksperimen lokal yang dicatat di `docs/evaluation/perf_matcher.md` mengklaim kesetaraan 200/200 dan median percepatan sekitar 6,9×, tetapi berkasnya belum dikomit dan belum menjadi runtime beku.

Tidak ada file beku, database, foto evaluasi, GT, threshold, atau hasil evaluasi yang diubah untuk laporan ini.
