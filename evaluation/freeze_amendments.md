# Catatan amendemen pasca-freeze

Tidak ada file beku yang diubah setelah `eval-freeze-v1`. Khususnya matcher, tokenizer, `evaluate_160_metrics.py`, `config_frozen.json`, KB, GT, threshold, dan daftar blokir tetap pada hash freeze.

Dua skrip baru ditambahkan setelah freeze:

- `evaluation/run_evaluate_160_parallel.py`: pembungkus paralel/resume untuk matcher dan classifier beku; memakai fungsi metrik beku setelah cache lengkap.
- `evaluation/package_final_evaluation_assets.py`: menyusun workbook, grafik, manifest, dan paket aset dari tabel evaluasi yang tersimpan.
- `evaluation/analyze_post_evaluation.py`: analisis deskriptif dari OCR/prediksi/metrik tersimpan; tidak memanggil OCR, matcher, atau classifier.

Bukti kesetaraan sebelum evaluasi 160 foto: seluruh prediksi 40 foto kalibrasi identik antara jalur sekuensial beku dan pembungkus (bahan, entri, kategori, verdict); metrik identik dengan selisih maksimum 0. Laporan mesin: `evaluation/results/evaluation_ocr/calibration_equivalence_report.json`. Hash matcher, tokenizer, classifier, config, KB, blokir pasangan, dan GT pada laporan tersebut sama dengan input beku yang diverifikasi wrapper.

Sesudah bukti itu lulus, pembungkus menjalankan matcher sekali pada cache OCR 160 foto. Aset pasca-evaluasi dibangun dari hasil tersimpan. Tidak ada freeze baru, tag baru, atau perubahan sistem yang dibuat oleh catatan ini.
