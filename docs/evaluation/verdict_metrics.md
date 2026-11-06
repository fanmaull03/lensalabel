# Metrik verdict produk

Verdict GT per foto adalah kategori bahan berisiko tertinggi yang tercatat di
GT: Hindari mengungguli Perlu Perhatian, yang mengungguli Aman. Evaluator
membandingkannya dengan verdict mentah classifier.

Confusion matrix tiga kelas memakai Aman, Perhatian, dan Hindari. Dua status
classifier yang menyatakan ketidakpastian, `perlu_verifikasi` dan
`tidak_terbaca`, dipetakan menjadi Perhatian di matriks itu agar seluruh foto
tetap terwakili. Pemetaan ini tidak menghapus status aslinya: file
`evaluation_verdict_status_cross_tab.csv` menampilkan silang lima status sistem
mentah terhadap tiga verdict GT, untuk keseluruhan foto dan masing-masing
kondisi. `evaluation_system_status_counts.csv` melaporkan jumlah produk pada
setiap status mentah, termasuk jumlah `perlu_verifikasi` dan `tidak_terbaca`.

Metrik verdict yang memiliki bootstrap CI dihitung dari matriks tiga kelas;
tabel silang dan jumlah status merupakan hitungan deskriptif. Resampling
memakai foto sebagai unit, 1000 iterasi, dan seed 42.
