# Ringkasan waktu pasca-evaluasi

Profil serial matcher lokal hanya mencakup enam sampel teks yang sudah diukur sebelum evaluasi penuh, bukan semua 160 foto. Angka per kondisi di bawah adalah ringkasan sampel gabungan antara teks evaluasi dan kalibrasi; evaluasi 160 sendiri dijalankan paralel dan tidak menyimpan durasi matcher per foto.

| Kondisi | N sampel | Rata-rata matcher | Median | Minimum | Maksimum |
|---|---:|---:|---:|---:|---:|
| datar | 2 | 25.05 dtk | 25.05 dtk | 21.11 dtk | 29.00 dtk |
| melengkung | 4 | 43.69 dtk | 16.05 dtk | 12.38 dtk | 130.29 dtk |

OCR Colab pada CSV evaluasi: rata-rata 2.61 detik/foto (160 foto). Perangkat tercatat lewat metadata runtime pada CSV.

Ablation menyimpan durasi per foto dan versi EasyOCR/Torch/OpenCV, tetapi tidak menyimpan status CUDA aktual atau nama GPU. Karena itu artefak tersebut tidak membuktikan adanya pengukuran OCR lokal CPU; angka waktu ablation disertakan di CSV terpisah tanpa mengatribusikannya ke CPU. Tidak ada OCR yang dijalankan ulang untuk membuat laporan ini.
