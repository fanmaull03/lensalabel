# Paket wawancara ahli gizi dan analisis fallback

Paket wawancara mengikuti Skema Ketiga Sub-bab 3.4.5 proposal: satu sesi ahli gizi setelah demonstrasi purwarupa, penilaian verdict, lalu penilaian kesesuaian dan keterpakaian penyajian. Pemilihan menggunakan split evaluasi, GT final, dan cache prediksi/OCR yang telah tersimpan. Tidak ada OCR atau matcher yang dijalankan ulang.

## Berkas paket

- `evaluation/results/expert_interview/paket_wawancara_ahli_gizi.pdf`: 16 kasus anonim. Bagian I memuat foto dan lembar verdict ahli tanpa keluaran sistem. Seluruh 16 verdict independen ditempatkan sebelum Bagian II, yang baru menampilkan keluaran ringkas aplikasi. Lembar kesesuaian dan catatan mengikuti tampilan kasus.
- `evaluation/results/expert_interview/template_respons_wawancara.xlsx`: tempat mencatat verdict ahli, kesesuaian, empat skor skala, dan jawaban terbuka.
- `evaluation/results/expert_interview/case_key_research_only.csv`: pemetaan ID W01–W16 ke filename dan jenis pemilihan; hanya untuk peneliti, tidak dimasukkan ke PDF ahli.
- `evaluation/results/expert_interview/packet_metadata.json`: seed, sumber, dan hash input.
- `docs/evaluation/expert_interview_instrument.md`: instrumen dan batas tampilan aplikasi yang dinilai.

Dua belas kasus acak dipilih dengan seed 42, enam dari kondisi datar dan enam melengkung. Empat kasus tambahan dipenuhi dari aturan tertulis: tepat satu bahan GT Hindari bersama bahan Aman/Perhatian; verdict sistem Perlu Verifikasi; GT Hindari dengan verdict sistem Perhatian yang dipilih acak memakai seed 42; dan verdict sistem Aman. Label jenis kasus hanya ada di kunci peneliti. Semua kasus tambahan berbeda dari 12 kasus acak.

## Pemeriksaan tampilan aplikasi

Antarmuka menampilkan verdict produk; daftar bahan per kategori; nama bahan, badge kategori, dan potongan teks yang terbaca. Rincian bahan menambahkan skor kemiripan, catatan umum sesuai kategori, dan disclaimer ilmiah umum. Tidak ada keterangan konsumsi spesifik per bahan yang disajikan aplikasi. Instrumen mengarahkan ahli menilai aspek tersebut berdasarkan tampilan generik yang benar-benar ada dan mencatat informasi yang masih dibutuhkan.

## Evaluasi fallback dari cache evaluasi

Definisi mengikuti `extract_composition_section()` dan marker fuzzy yang sama: fallback pembuka terjadi saat penanda pembuka tidak ditemukan sehingga seluruh teks OCR dipakai; fallback penutup terjadi bila pembuka ditemukan tetapi marker penutup tidak ditemukan. Untuk kelompok fallback penutup, denominator hanya foto yang marker pembukanya ditemukan. Metrik bahan memakai nama bahan kanonis dan menjumlahkan TP/FP/FN per foto; satu bahan pada dua produk adalah dua observasi. CI adalah percentile bootstrap per foto, 1.000 resampling, seed 42. Kelompok di bawah 20 foto ditandai deskriptif; CI tetap disertakan jika kelompok tidak kosong. Hasil rinci dan interval tersimpan pada `evaluation/results/expert_interview/fallback_frequency.csv` dan `fallback_metrics_by_group.csv`.

| Kondisi | Foto | Pembuka tidak ditemukan | Pembuka ditemukan | Penutup tidak ditemukan (di antara pembuka ditemukan) |
|---|---:|---:|---:|---:|
| Keseluruhan | 160 | 5 | 155 | 48 |
| Datar | 80 | 0 | 80 | 6 |
| Melengkung | 80 | 5 | 75 | 42 |

### Metrik bahan: fallback pembuka

| Kondisi | Kelompok (foto) | Precision [CI 95%] | Recall [CI 95%] | F1 [CI 95%] |
|---|---:|---:|---:|---:|
| Keseluruhan | Fallback (5) | 0,654 [0,483–0,870] | 0,436 [0,324–0,537] | 0,523 [0,414–0,622] |
| Keseluruhan | Non-fallback (155) | 0,758 [0,733–0,782] | 0,699 [0,668–0,731] | 0,727 [0,704–0,749] |
| Datar | Fallback (0) | — | — | — |
| Datar | Non-fallback (80) | 0,785 [0,752–0,817] | 0,733 [0,693–0,772] | 0,758 [0,729–0,788] |
| Melengkung | Fallback (5) | 0,654 [0,483–0,870] | 0,436 [0,324–0,537] | 0,523 [0,414–0,622] |
| Melengkung | Non-fallback (75) | 0,723 [0,690–0,755] | 0,653 [0,604–0,706] | 0,686 [0,651–0,721] |

### Metrik bahan: fallback penutup

| Kondisi | Kelompok (foto) | Precision [CI 95%] | Recall [CI 95%] | F1 [CI 95%] |
|---|---:|---:|---:|---:|
| Keseluruhan | Fallback (48) | 0,675 [0,615–0,729] | 0,649 [0,579–0,712] | 0,662 [0,607–0,707] |
| Keseluruhan | Non-fallback (107) | 0,793 [0,769–0,813] | 0,719 [0,681–0,755] | 0,754 [0,728–0,779] |
| Datar | Fallback (6) | 0,567 [0,409–0,760] | 0,829 [0,739–0,909] | 0,673 [0,532–0,821] |
| Datar | Non-fallback (74) | 0,803 [0,776–0,828] | 0,728 [0,687–0,769] | 0,764 [0,735–0,793] |
| Melengkung | Fallback (42) | 0,695 [0,640–0,744] | 0,629 [0,559–0,697] | 0,660 [0,609–0,708] |
| Melengkung | Non-fallback (33) | 0,763 [0,723–0,794] | 0,689 [0,615–0,751] | 0,724 [0,673–0,766] |

Kelompok fallback pembuka hanya lima foto, dan kelompok fallback penutup datar hanya enam foto; perbandingan keduanya bersifat deskriptif, bukan kesimpulan inferensial. Semua metrik dan CI tersedia pada CSV hasil agar dapat ditelusuri tanpa membuka ulang prediksi atau menjalankan matcher.

## Analisis respons ahli

`evaluation/analyze_expert_interview.py` menerima template workbook yang telah diisi. Skrip menghasilkan persentase kesepakatan dan Cohen's kappa ahli-vs-sistem serta ahli-vs-GT, masing-masing untuk 12 kasus acak dan seluruh 16 kasus; proporsi tiga jawaban kesesuaian; ringkasan skor empat aspek; dan hitungan produk GT Hindari yang dinilai Aman oleh ahli. Verdict sistem Perlu Verifikasi dan Tidak Terbaca dipetakan ke Perhatian untuk perbandingan tiga kelas, konsisten dengan konvensi evaluasi beku. Respons kosong/tidak valid tidak dimasukkan ke statistik pasangan dan dilaporkan terpisah.

Uji dummy: `evaluation/tests/test_expert_interview_analysis.py` memeriksa agreement 75%, kappa 0,6, statistik skala, dan masukan kosong. Tidak ada data kontak ahli yang diminta atau disimpan.
