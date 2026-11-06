# Kalibrasi v4 dan langkah Colab

Daftar final berisi 10 pasangan terlarang: Kalium/Kalsium, tujuh usulan dari audit, Baking/Caking, dan Sweetened/Sweetener. Delapan pasangan ejaan/jamak tetap toleran. Kode INS/E dan token berangka wajib cocok persis. Lenient tidak melintasi koma pemisah item atau kurung; koma desimal tetap diperbolehkan.

Longest-match-wins lenient hanya berlaku untuk Minyak kelapa -> Minyak kelapa sawit. Inventaris 69 relasi tetap disimpan di `evaluation/lenient_taxonomy_review_pairs.json`. Relasi selain kelapa/sawit hanya menandai kandidat yang benar-benar berbagi kata dalam kemunculan frasa yang sama, dengan sumber `ambigu_taksonomi_tunggu_ahli_gizi`. Penandaan tidak menetapkan taksonomi klinis dan tidak mengganti keputusan manual.

## Hasil v4

| Item | Jumlah |
|---|---:|
| Kandidat hasil deteksi otomatis | 29 |
| Y lama yang dipertahankan meskipun terfilter otomatis | 5 |
| Total kandidat aktif di v4 | 34 |
| Keputusan Y terbawa dengan kunci persis | 30 |
| Keputusan N terbawa dengan kunci persis | 4 |
| Kandidat baru / keputusan kosong aktif | 0 |
| Kandidat bertanda ambigu taksonomi | 12 (8 Y, 4 N) |
| Arsip nonaktif v2 | 16 (15 N, 1 kosong) |
| Strict GT | 362 |
| GT final setelah merge | 392 |

Keputusan dicocokkan persis pada `(filename, standard_name, matched_variant)`. Lima Y yang terfilter dicatat sebagai `DIPERTAHANKAN_MANUAL`, tetap aktif sesuai instruksi pengguna, tanpa melonggarkan matcher. Sheet `arsip_nonaktif_v2` tidak ikut merge. Kedua perisa pada melengkung_092.jpeg, Paprika bubuk pada datar_015.jpeg, Susu bubuk pada melengkung_014.jpeg, dan Krimer susu bubuk pada melengkung_055.jpeg merupakan lima keputusan yang dipertahankan manual.

Karena tidak ada keputusan aktif kosong, merge dilanjutkan sesuai instruksi setelah review lengkap. Skrip merge membaca nama kolom dan menolak keputusan aktif kosong, kategori/varian yang tidak cocok KB, serta filename di luar strict GT. Anotasi manual final menyimpan ID bahan, matched_variant, dan sumber review.

```powershell
backend\.venv\Scripts\python.exe evaluation\generate_calibration_review.py --review-v4
backend\.venv\Scripts\python.exe evaluation\merge_reviewed_gt.py --review-xlsx dataset/ground_truth/calibration_review_v4.xlsx --summary-json evaluation/results/calibration_merge_v4_summary.json
backend\.venv\Scripts\python.exe evaluation\build_colab_calibration_bundle.py
```

Output v4 dan bundle yang sudah ada dilindungi dari penimpaan; arsipkan dahulu jika sengaja membuat ulang setelah review berubah. GT final berbeda juga tidak ditimpa otomatis.

## Menjalankan Colab

1. Buka `evaluation/notebooks/calibration_grid_search_colab.ipynb` melalui **File > Upload notebook** di Colab. Notebook `.ipynb` dapat diimpor melalui menu ini menurut [FAQ resmi Colab](https://research.google.com/colaboratory/faq.html).
2. Pilih runtime GPU melalui **Runtime > Change runtime type**, lalu jalankan sel berurutan. Pengaturan runtime dijelaskan pada [FAQ Colab](https://research.google.com/colaboratory/faq.html). Notebook memakai CUDA bila tersedia melalui opsi GPU [EasyOCR](https://jaided.ai/easyocr/documentation/).
3. Pada sel unggah, pilih `evaluation/results/lensalabel_calibration_v4_bundle.zip`. Paket berisi 40 foto kalibrasi, GT final, KB snapshot, dan modul yang digunakan. Manifest SHA-256 diperiksa sebelum OCR.
4. Jalankan cache OCR sekali untuk seluruh 40 foto. Cache yang sudah lengkap dalam folder hasil yang sama akan dilewati pada pengulangan sel. Unduh paket hasil sebelum menutup runtime.
5. Jalankan grid threshold **70, 75, 80, 85, 90, 95** dari `run_grid_search.py`. Bobot similarity, preprocessing, closing-marker, dan reading-order menggunakan kode workspace yang sudah final. Grid ini menguji threshold; tidak mengubah bobot atau parameter produksi.
6. Unduh ZIP hasil yang memuat cache OCR, CSV detail/summary, versi lingkungan, dan pilihan threshold terbaik pada kalibrasi. Tie-break: F1 tertinggi, kemudian precision tertinggi, kemudian threshold terendah. Pilihan ini dicatat; parameter produksi tidak langsung ditimpa.

160 foto evaluasi tidak dimasukkan ke paket dan tidak dipakai memilih threshold. Kandidat evaluasi nanti perlu dibuat memakai helper lenient yang sama dan keputusan manual sebelum evaluasi akhir.

Notebook dan bundle telah disiapkan lokal. Eksekusi OCR/grid pada runtime Colab belum dijalankan; hasil grid tidak diisi dengan data simulasi.

Verifikasi akhir: 39 tes anotasi/merge lulus, 30 kunci persetujuan Y tetap persis, 10 file sumber yang dilindungi dan 200 foto tetap sama. Matcher saat ini menghasilkan kembali 29 kandidat otomatis v4 yang identik. Sintaks sel notebook dan CLI OCR/grid diperiksa; seluruh 60 file di ZIP cocok dengan manifest SHA-256. Paket berukuran 105,8 MiB. Laporan mesin tersimpan di `evaluation/results/calibration_v4_verification.json`.
