# Bukti kesetaraan matcher untuk `app-hosting-fast`

Pengukuran 16 Oktober 2026. Default aplikasi tetap `MATCHER_MODE=frozen`; mode `optimized` memilih modul terpisah. `backend/app/matching/fuzzy_matcher.py` tidak diubah dan SHA-256-nya `289686a7a8a0bdf3528cfde1605b8c3633f8e82e29a752fb1c737390f5c2af13`, sama dengan isi tag `eval-freeze-v1`. Modul `fuzzy_matcher_optimized.py` adalah salinan byte-identik dari commit `perf-matcher` `1cf26fd`, SHA-256 `ad66445adcf569e397693eff68d999796c1ed153b642d51038ae25c31020bdfb`.

## Prediksi lengkap

Laporan `evaluation/results/post_eval_supplement/perf_full_equivalence_200.json` telah membandingkan 160 teks OCR evaluasi tersimpan dan 40 teks OCR kalibrasi tersimpan: **200/200 identik** untuk seluruh entri, match, skor, kategori, dan verdict. Skrip `backend/tools/differential_matchers.py` menerima bukti lama itu hanya bila SHA-256 kedua modul sama; SHA-256 kedua cache OCR, kedua cache prediksi, konfigurasi, KB, dan daftar blokir juga diperiksa terhadap provenance uji lama. Tidak ada OCR baru pada 160 foto evaluasi.

Uji baru memakai 2.000 **teks unik** dari fragmen transkrip GT, seed 42. Gangguan mencakup penambahan karakter, penghapusan karakter, penukaran huruf, pemotongan token, penghilangan koma antarbutir, negasi, dan pola kepala bersama. Kedua modul dijalankan pada setiap teks dengan KB v2, threshold 75, bobot sepertiga, dan penalti panjang 0,8. Prediksi dibandingkan sebagai struktur lengkap (`MatchResult` beserta skor dan span, hasil klasifikasi, serta verdict): **2.000/2.000 identik, 0 selisih**. Keluaran lokal: `evaluation/results/post_eval_supplement/app_hosting_fast_differential_2200.json` (artefak riset di luar cabang deploy).

| Korpus sintetis | n | Rata-rata beku → cepat (dtk) | Median beku → cepat | p95 beku → cepat | Rasio rata-rata |
|---|---:|---:|---:|---:|---:|
| Datar | 1.082 | 0,984 → 0,685 | 0,687 → 0,480 | 2,834 → 2,016 | 1,44× |
| Melengkung | 918 | 0,906 → 0,597 | 0,638 → 0,420 | 2,598 → 1,594 | 1,52× |
| Semua | 2.000 | 0,948 → 0,644 | 0,664 → 0,459 | 2,736 → 1,861 | 1,47× |

Waktu di atas adalah waktu matcher dan klasifikasi pada teks sintetis; itu bukan waktu OCR atau latensi HTTP. Empat proses dipakai untuk pengujian diferensial pada laptop Windows. Rasio dihitung dari ringkasan masing-masing modul.

## Tiga foto kalibrasi di laptop

Foto hanya dari split kalibrasi. Setiap foto di-OCR **satu kali** pada lebar 1500 dan adaptive threshold OFF; teks yang sama kemudian dipakai kedua matcher. Prediksi keduanya identik pada ketiga foto. Waktu proses lokal dalam detik:

| Foto | OCR | Matcher beku | Matcher cepat | Total beku | Total cepat |
|---|---:|---:|---:|---:|---:|
| melengkung_076.jpeg | 56,78 | 18,52 | 11,88 | 76,04 | 69,40 |
| datar_095.jpeg | 67,86 | 6,95 | 7,52 | 75,58 | 76,15 |
| datar_015.jpeg | 89,58 | 37,96 | 22,24 | 128,21 | 112,49 |

Total mencakup dekode, prapemrosesan, OCR, ekstraksi/tokenisasi, dan matcher/klasifikasi. Pemuatan model sekali pada pengukuran ini 32,46 detik; permintaan pertama termasuk pemuatan model menjadi 108,51 detik (beku) atau 101,87 detik (cepat). Profil sebelumnya mencatat sekitar 14 detik pemuatan dan 54 detik permintaan pertama, sehingga cold start bervariasi dan harus diukur lagi pada host. Pada `datar_095` mode cepat sedikit lebih lambat dalam satu pengukuran; OCR tetap komponen dominan.

Uji asap HTTP lokal memakai tiga foto kalibrasi asli sebagai unggahan tetapi memutar ulang OCR tersimpan di sisi server agar perbandingan API/matcher deterministik: **3/3 cocok pada mode beku dan 3/3 cocok pada mode cepat**. Uji ini tidak membuktikan kesetaraan OCR lintas perangkat. Skrip `backend/tools/deploy_smoke_test.py` siap menerima folder 16 foto wawancara dan berkas pemetaan ID anonim yang disimpan di luar Git.
