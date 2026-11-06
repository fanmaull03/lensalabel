# Koreksi GT dan perbandingan matcher — 7 Oktober 2026

## Data

`dataset/ground_truth/transcripts.csv` kembali berisi 200 filename unik. Transcript baru datar_047 dan melengkung_049 memakai teks yang diberikan pengguna. Angka `Bubuk Kakao 0.4%` di melengkung_003 menjadi `0.8%`; `Gom selan` di melengkung_017 menjadi `Gom gelan`. Transcript datar_049 yang sudah dikonfirmasi tidak diubah lagi.

Jika dibandingkan dengan dataset sebelum seluruh koreksi, ada tujuh baris berbeda: datar_047/048/049 dan melengkung_003/017/049/050. Lima berasal dari cluster salah pasang, dua dari koreksi lokal. Datar_050 dan melengkung_060 tetap identik.

Split yang tersimpan menempatkan **datar_047 di evaluasi**, bukan kalibrasi. Split 40/160 dipertahankan. Dari ketujuh baris tersebut, hanya melengkung_049 berada di kalibrasi. Anotasi datar_047 disimpan terpisah di `dataset/ground_truth/datar_047_ingredients_gt_final.json` dan tidak dipakai dalam grid.

Kedua transcript baru menjalani fungsi strict dan lenient anotasi yang sama dengan v4: masing-masing 10 bahan strict, tanpa kandidat lenient baru. GT final kalibrasi kembali mencakup tepat 40 filename dengan **396 anotasi** (sebelumnya 392). Enam anotasi lama melengkung_049 diganti 10 anotasi baru; 39 entri lain identik. Strict GT untuk foto ini juga diperbarui. Excel review lama tidak diubah.

Baseline 40 foto/392 anotasi diambil dari cadangan sebelum koreksi `dataset/ground_truth/correction_history/20261006_145456_transcript_mapping/calibration_ingredients_gt_final.json`. Cadangan tambahan sebelum perubahan sesi ini ada di `evaluation/results/gt_matcher_revision/before/`.

## Implementasi

`backend/app/matching/fuzzy_matcher.py` mempertahankan seluruh fungsi lama, termasuk `match_token`, `composite_score`, dan fungsi negasi. Kesamaan AST fungsi-fungsi tersebut diverifikasi terhadap salinan sebelum perubahan.

`match_token_many` memilih skor tertinggi, menggunakan preferensi panjang pada skor sama dan urutan KB yang stabil. Rentang sumber yang sudah dipilih dikonsumsi; fragmen kiri dan kanan dipindai terpisah. Span kandidat yang ditolak negasi juga dikonsumsi agar alias lebih pendek tidak lolos dari penyebutan yang sama. Offset karakter tersimpan dalam `span_start`/`span_end`. Skor dan hasil terbaik per fragmen disimpan dalam cache LRU terbatas, dengan teks, varian dan bobot sebagai bagian kuncinya.

Pola kepala bersama hanya menerima `Dinatrium Inosinat dan Guanilat` dan urutan sebaliknya, exact tanpa membedakan kapitalisasi, dan mensyaratkan dua nama lengkap ada di KB. Tidak melintasi koma, kurung, atau kata sisipan. Kandidat kedua menyimpan span ekor, span kepala bersama, dan `match_source=shared_head`; skor dihitung dengan fungsi skor yang sama. Jika konteks pola terdeteksi negatif, parser abstain pada frasa tersebut. Ini tidak menambahkan sinonim global atau aturan scope negasi baru.

Pipeline API dan grid menggunakan fungsi baru; `--matcher old` tersedia untuk reproduksi baseline dan `--matcher many` untuk ablasi kepala bersama. Classifier tidak berubah. Pada token yang memiliki match positif, sisa qualifier/noise tidak dijadikan status unknown baru, mengikuti granularitas unknown per token sebelumnya.

Batas yang masih berlaku: negasi lama mengacu pada kemunculan pertama alias dalam token; penyebutan berulang dengan konteks berbeda tidak diselesaikan dalam perubahan ini. Penanganan kepala bersama tidak memperbaiki OCR yang menyisipkan tabel gizi di tengah frasa. Perbaikan ini juga tidak memperluas aturan taksonomi atau daftar pasangan kimia helper anotasi ke matcher produksi. Default threshold produksi tetap seperti sebelum perubahan, tidak dipilih otomatis dari grid.

## Validasi

- Suite `backend/tests` dan `evaluation/tests`: 87 tes dan 80 subtes lulus.
- Pemeriksaan integrasi `_classify_text` dan skema API: dua bahan dalam satu token serta pola kepala bersama berhasil masuk respons classifier.
- 211 berkas yang dicatat sebelum perubahan tetap identik: foto, workbook lama, split, KB snapshot, reader dan tokenizer. Bukti ada di `evaluation/results/gt_matcher_revision/data_verification.json`.
- Grid membandingkan prediksi baseline pada seluruh 240 kombinasi foto/threshold dengan hasil Colab sebelumnya; kegagalan kecocokan menghentikan eksperimen.

## Menjalankan Colab

1. Buka `evaluation/notebooks/gt_matcher_comparison_colab.ipynb` di Colab.
2. Run all dan unggah `evaluation/results/gt_matcher_revision/lensalabel_gt_matcher_comparison_bundle.zip` saat diminta.
3. Setelah selesai, unduh ZIP hasil. Ekstrak ke `evaluation/results/`, sehingga hasil berada di `gt_matcher_revision_colab/`.

Bundle hanya memuat kode, dua versi GT, KB, split, dan 40 cache OCR; tidak memuat foto evaluasi. OCR tidak dijalankan ulang karena tidak ada perubahan foto. Matching memakai CPU, sehingga runtime GPU tidak wajib. SHA-256 semua input ZIP diperiksa notebook sebelum eksekusi.

Belum ada akses dari workspace ini ke runtime Colab pengguna. Hasil replay lokal dan hasil Colab harus dibedakan; notebook yang sudah disiapkan bukan bukti eksekusi Colab.

## Berkas hasil

Replay lokal tersimpan di `evaluation/results/gt_matcher_revision/local_comparison/`:

- `comparison_summary.csv`: keempat kondisi pada enam threshold.
- `comparison_detail.csv`: TP/FP/FN per foto dan daftar bahan.
- `prediction_changes.csv`: FN yang pulih dan FP tambahan pada GT baru, beserta bukti match.
- `match_traces.json`: token, skor, offset dan provenance.
- `run_manifest.json`: kelengkapan, hash input, runtime dan verifikasi baseline.
- `matcher_timing.csv`: waktu eksekusi; bukan benchmark cold-cache, karena matcher lama dihitung sekali per token dan matcher baru memakai cache terbatas.

Perbandingan a→b memisahkan pengaruh koreksi GT; b→c mengukur perubahan matcher pada GT yang identik. Ablasi `many_only` memisahkan dampak multi-match dari kepala bersama. Ambang akhir tetap perlu ditinjau berdasarkan precision, recall dan FP baru.

## Hasil lokal lengkap

Seluruh 40 foto × 6 threshold × 4 kondisi selesai (960 baris detail). Semua 240 prediksi baseline identik dengan hasil Colab lama; hash sumber, GT dan cache saat akhir eksekusi masih sesuai. **Angka berikut berasal dari replay lokal Windows, bukan eksekusi Colab baru.**

Pada threshold yang sama, **70**:

| Kondisi | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| (a) GT lama + matcher lama | 224 | 30 | 168 | 88,19% | 57,14% | 0,6935 |
| (b) GT baru + matcher lama | 228 | 26 | 168 | 89,76% | 57,58% | 0,7015 |
| (c) GT baru + matcher baru | 296 | 71 | 100 | 80,65% | 74,75% | 0,7759 |

Koreksi GT sendiri memberi tambahan 4 TP dan mengubah 4 FP menjadi TP; recall naik 0,43 poin persentase. Perubahan matcher pada GT identik memulihkan **68 FN**, menambah **45 FP**, dan menaikkan recall **17,17 poin persentase**. Precision turun 9,11 poin persentase; kenaikan recall bukan tanpa biaya.

F1 tertinggi matcher baru pada enam threshold yang diuji adalah **75**, dengan TP 282, FP 46, FN 114, precision 85,98%, recall 71,21%, dan F1 **0,7790**. Pada 80, precision 92,23%, recall 65,91%, F1 0,7688. Ini hasil eksplorasi, bukan perubahan konfigurasi threshold otomatis.

Kondisi `many_only` dan `many_shared` menghasilkan metrik serta prediksi yang identik di semua threshold. Tidak ada match positif dengan provenance `shared_head` pada OCR 40 foto ini. Dengan demikian, kenaikan terukur berasal dari **Prioritas 2**; implementasi Prioritas 3 lulus pengujian pola terkontrol tetapi belum menunjukkan tambahan recall pada sampel ini. OCR yang memisahkan pola dengan teks lain tetap tidak diperbaiki, sesuai pembatasan parser.

Contoh FP tambahan terhadap GT: `Minyak Nabati` dinilai mirip `Minyak zaitun` pada skor 70,42 (datar_029/032). Ada pula `Flavour Enhancer` → varian `Flavor enhancer` pada skor 90,28 dan `Butter` → `Butter` pada skor 100. Karena sebagian FP adalah exact match di OCR, status FP di tabel berarti tidak ada di GT, bukan otomatis bukti bahwa ejaan matcher salah; kasus tersebut memerlukan peninjauan teks/GT terpisah. Tidak ada perubahan GT atau aturan tambahan untuk menghilangkan FP berdasarkan hasil eksperimen ini.

Kontinuitas review diverifikasi dengan merge dalam memori: 366 strict + **30 keputusan Y lama**, 4 keputusan N, menghasilkan tepat GT final tersimpan berisi 396 anotasi. Tidak ada workbook lama yang ditimpa.
