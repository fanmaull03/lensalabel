# Cabang eksperimen `perf-matcher`

Perubahan ini hanya ada di cabang `perf-matcher`, dibuat dari `main` setelah tag `eval-results-v1`. `main` dan tag tidak dipindah atau diubah. Cabang belum digabung.

Optimasi hanya mengubah cara kerja internal pencarian kandidat di `match_token_many`:

- Lebar jendela kata untuk setiap varian KB disimpan di cache, dan string/span jendela yang sama dibangun sekali per fragmen.
- Peta bobot dan pemeriksaan pasangan kimia disimpan di cache.
- Sebelum menghitung skor penuh, gunakan batas atas aman dari penalti panjang: `round(100 * (min_len/max_len)**exponent, 2)`. Karena tiap komponen skor maksimum 100, kandidat dengan batas atas di bawah threshold tidak mungkin diterima dan dilewati. Kandidat yang batas atasnya sama dengan atau lebih tinggi dari threshold tetap dinilai penuh.
- Kandidat di bawah threshold yang mustahil mencapai threshold tidak lagi menyimpan nilai “terdekat” yang rinci. Status unmatched tetap dipertahankan. Karena itu pembuktian kesetaraan membandingkan seluruh bahan terpilih beserta ID entri dan kategori, serta verdict produk, sesuai kriteria; metadata skor kandidat unmatched bukan target kesetaraan.

## Bukti kesetaraan

Skrip `evaluation/benchmark_perf_matcher_200.py` memproses 40 teks OCR kalibrasi 1500/OFF dan 160 teks OCR evaluasi yang telah tersimpan. Hasil matcher dibandingkan dengan cache beku pada kunci `(ingredient_id, standard_name, category)` serta verdict produk.

- Foto yang diperiksa: 200/200.
- Prediksi inti berbeda: 0.
- Threshold: 75.

File hasil: `evaluation/results/post_eval_supplement/perf_matcher_equivalence_200.json`.

## Percepatan terukur

Enam teks OCR profil lama diproses ulang secara serial dengan cabang ini dan jam aktif Windows. Teks OCR sumber sama dengan profil lama.

| Foto | Matcher lama | Cabang perf | Percepatan |
|---|---:|---:|---:|
| datar_044.jpeg | 21,11 dtk | 3,00 dtk | 7,04× |
| datar_015.jpeg | 29,00 dtk | 4,26 dtk | 6,81× |
| melengkung_038.jpeg | 12,38 dtk | 1,77 dtk | 7,00× |
| melengkung_097.jpeg | 130,29 dtk | 17,77 dtk | 7,33× |
| melengkung_076.jpeg | 16,07 dtk | 2,50 dtk | 6,43× |
| melengkung_014.jpeg | 16,03 dtk | 3,07 dtk | 5,22× |

Median percepatan 6,90×; rata-rata 6,64×. Rincian tersimpan di `evaluation/results/post_eval_supplement/perf_matcher_profile_comparison_activeclock.csv`.

Pengukuran lokal 20 foto kalibrasi di `timing_summary.md` juga memakai cabang ini. Satu versi timing awal memakai `perf_counter` dan dapat terpengaruh suspend laptop; angka itu telah diganti dengan jam aktif Windows. Karena keseluruhan benchmark 200 foto pertama memakai timer yang sama, waktu benchmark totalnya tidak dipakai sebagai klaim performa. Kesetaraan 200/200 tetap sah karena seluruh output inti selesai dibandingkan dengan cache.

Pengujian unit matcher/secondary guard setelah perubahan: 46 passed. Suite backend+evaluasi penuh menghasilkan 167 passed, 1 xfailed, 86 subtests passed, dan satu kegagalan pada `test_draft_config_blocks_final_workflows`: tes meminta `status == "draft"`, sementara konfigurasi saat ini memang sudah dibekukan. Tanpa mengubah konfigurasi beku, suite selain pemeriksaan status draft tersebut lulus: 167 passed, 1 deselected, 1 xfailed, 86 subtests passed. Untuk mengulang suite lengkap:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests evaluation/tests -q
```

Penggunaan masih eksperimental sampai pemilik proyek meninjau cabang ini. Perubahan belum diterapkan ke konfigurasi beku, hasil evaluasi, `main`, atau tag.
