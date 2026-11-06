# Analisis pasca-evaluasi 160 foto

Analisis ini hanya membaca `evaluation_ocr_160.csv`, cache prediksi JSONL, GT final, dan tabel metrik yang sudah disimpan. OCR, matcher, classifier, metrik evaluasi beku, GT, KB, dan konfigurasi tidak dijalankan ulang atau diubah. Bootstrap memakai 1.000 resampling per foto dan seed 42.

## Verdict produk

GT terdiri dari 5 Aman, 39 Perlu Perhatian, dan 116 Hindari. Baseline yang selalu memilih kelas mayoritas (Hindari) memiliki akurasi 0,725 (CI 95% 0,656–0,794). Sistem memiliki akurasi 0,731 (0,663–0,794), macro-F1 0,552 (0,425–0,688), dan Cohen's kappa 0,437 (0,295–0,560). CI dihitung dengan bootstrap foto menggunakan resampling NumPy `default_rng(42)` dan kuantil 2,5%/97,5%.

### Matriks konfusi 3 kelas

Baris adalah verdict GT; kolom adalah verdict sistem setelah status `perlu_verifikasi` dan `tidak_terbaca` dipetakan menjadi Perlu Perhatian.

| GT \\ Sistem | Aman | Perlu Perhatian | Hindari | Total GT |
|---|---:|---:|---:|---:|
| Aman | 1 | 3 | 1 | 5 |
| Perlu Perhatian | 2 | 30 | 7 | 39 |
| Hindari | 0 | 30 | 86 | 116 |

### Status sistem 5 kelas terhadap verdict GT 3 kelas

| Status sistem | GT Aman | GT Perlu Perhatian | GT Hindari |
|---|---:|---:|---:|
| Aman | 1 | 2 | 0 |
| Perhatian | 2 | 25 | 28 |
| Hindari | 1 | 7 | 86 |
| Perlu Verifikasi | 1 | 5 | 2 |
| Tidak Terbaca | 0 | 0 | 0 |

Di antara 116 produk GT Hindari, 28 berstatus sistem Perhatian dan 2 Perlu Verifikasi; tidak ada yang berstatus Aman. Nama 30 foto tersebut disimpan terpisah di `evaluation/results/post_evaluation/gt_hindari_missed_photo_names.csv` dan sengaja tidak dicantumkan di laporan ini.

## Penyebab kesalahan bahan

`error_cause_summary_by_condition.csv` mengelompokkan seluruh event FP/FN dengan heuristik tetap. Kategori berikut bersifat indikatif, bukan bukti sebab-akibat. Urutan aturan membuat setiap event masuk ke satu kategori:

- FP teks luar komposisi: token match memuat penanda seperti *Takaran Saji*, *Nutrition Facts*, *Energi Total*, *Lemak Total*, *Karbohidrat Total*, atau klaim bebas gluten/susu. Jika marker pembuka gagal, penanda tersebut boleh dicari pada teks OCR penuh.
- FP pernyataan mengandung/alergen: setelah aturan luar-komposisi, token match berada pada konteks `mengandung`, `contains`, `may contain`, `dapat mengandung`, atau `alergen`.
- FP alias generik vs spesifik: setelah dua aturan pertama, span match dan variant GT merupakan substring satu sama lain, tetapi entri berbeda dan kategori sama.
- FP kemiripan string salah entri: setelah aturan di atas, match KB memiliki skor komposit <100.
- Sisa FP dilaporkan sebagai tidak terklasifikasi; tidak dipaksakan ke salah satu penyebab.
- FN marker memotong bahan hanya dicatat jika variant GT mencapai partial-ratio ≥90 pada suffix OCR setelah teks hasil ekstraksi. Tidak ada kasus yang memenuhi bukti langsung itu. Marker pembuka yang gagal terdeteksi menghasilkan fallback seluruh teks, sehingga dengan sendirinya tidak memotong bahan.
- FN cakupan KB diperiksa berikutnya: variant GT tidak ditemukan dalam nama maupun alias mana pun di KB.
- Jika variant tidak ada pada KB, kategori berikutnya membandingkan partial-ratio variant GT terhadap komposisi OCR: skor ≥75 berarti kandidat teks cukup dekat tetapi tidak terpilih; label ini mencakup threshold, seleksi span, dan overlap. Skor <75 berarti salah baca atau hilang dari OCR.

| Jenis | Kondisi | Total | Penyebab | Jumlah | Proporsi |
|---|---|---:|---|---:|---:|
| FP | Datar | 166 | Teks luar komposisi | 7 | 4,2% |
| FP | Datar | 166 | Kemiripan string salah entri | 53 | 31,9% |
| FP | Datar | 166 | Alias generik, kategori sama | 16 | 9,6% |
| FP | Datar | 166 | Pernyataan mengandung/alergen | 19 | 11,4% |
| FP | Datar | 166 | Tidak terklasifikasi | 71 | 42,8% |
| FP | Melengkung | 166 | Teks luar komposisi | 13 | 7,8% |
| FP | Melengkung | 166 | Kemiripan string salah entri | 68 | 41,0% |
| FP | Melengkung | 166 | Alias generik, kategori sama | 5 | 3,0% |
| FP | Melengkung | 166 | Pernyataan mengandung/alergen | 23 | 13,9% |
| FP | Melengkung | 166 | Tidak terklasifikasi | 57 | 34,3% |
| FN | Datar | 220 | OCR salah baca/hilang | 100 | 45,5% |
| FN | Datar | 220 | Marker menutup bahan | 0 | 0,0% |
| FN | Datar | 220 | Variant tidak ada di KB | 0 | 0,0% |
| FN | Datar | 220 | Kandidat ada, tidak dipilih threshold/seleksi | 120 | 54,5% |
| FN | Melengkung | 239 | OCR salah baca/hilang | 131 | 54,8% |
| FN | Melengkung | 239 | Marker menutup bahan | 0 | 0,0% |
| FN | Melengkung | 239 | Variant tidak ada di KB | 0 | 0,0% |
| FN | Melengkung | 239 | Kandidat ada, tidak dipilih threshold/seleksi | 108 | 45,2% |

Lima contoh acak seed 42 untuk setiap penyebab yang memiliki kasus tersedia ada di `evaluation/results/post_evaluation/error_examples_seed42.csv`. Berkas mencantumkan nama foto, cuplikan OCR, bahan GT, bahan prediksi, dan bukti span/skor. Untuk kelas penyebab yang berjumlah nol, tidak ada contoh.

## Ekstraksi komposisi

| Kondisi | Foto | Pembuka tidak terdeteksi | Rata-rata rasio panjang hasil ekstraksi / transkrip GT |
|---|---:|---:|---:|
| Datar | 80 | 0 | 1,696 |
| Melengkung | 80 | 5 | 2,606 |

Rasio menggunakan jumlah karakter mentah per foto, lalu dirata-ratakan; nilainya dapat melebihi 1 karena OCR menyisipkan/merusak teks. Kegagalan marker pembuka menyebabkan extractor menggunakan teks penuh (fallback), bukan memotongnya.

## Artefak

Ringkasan lengkap, matriks, cross-tab, contoh, data ekstraksi, dan provenance ada di `evaluation/results/post_evaluation/`. Grafik agregat ada di `evaluation/results/chapter4/`. Daftar foto untuk GT Hindari yang terlewat disimpan terpisah, bukan ditampilkan di chat.
