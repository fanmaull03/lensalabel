# Handoff Konteks: LensaLabel — Evaluasi Ulang Pasca-Penyelarasan KB v2

Dokumen ini berisi konteks kerja untuk melanjutkan proyek skripsi LensaLabel di AI atau sesi lain. Dokumen mencakup keputusan metodologis, temuan verifikasi, artefak yang sudah dibuat, dan langkah yang belum selesai per 31 Oktober 2026.

Bacalah dokumen ini sepenuhnya sebelum bertindak. Jangan menganggap angka pada BAB IV laporan saat ini masih valid.

---

## 1. Ringkasan status terbaru

Pekerjaan revisi BAB IV berubah arah pada 31 Oktober 2026. Bukan lagi sekadar merapikan naskah, tetapi **membangun ulang baseline evaluasi** karena ditemukan dua masalah data:

1. Ground truth evaluasi memakai `standard_name` lama yang sudah tidak ada di KB v2.
2. Ground truth evaluasi memakai **kategori** lama yang berbeda dari kategori KB v2.

Karena itu seluruh angka BAB IV yang sekarang ada di laporan berasal dari data yang tidak konsisten dengan KB v2 dan dengan kode yang benar-benar di-deploy. Baseline baru sedang dibangun.

**Yang sudah selesai:** penyelarasan GT evaluasi ke KB v2, kalibrasi ulang 6 konfigurasi, penetapan konfigurasi beku v2.
**Yang belum selesai:** OCR ulang 160 foto, evaluasi akhir, regenerasi seluruh tabel/gambar BAB IV, dan pembaruan angka di laporan Word.

---

## 2. Preferensi pengguna dan aturan kerja

- Bahasa: Bahasa Indonesia akademik, lugas, tidak bertele-tele.
- Pengguna ingin revisi tiap subbab **bukan hanya memangkas teori**, tetapi juga mempertimbangkan penambahan gambar, diagram, screenshot, atau tabel agar isi lebih kuat. Setiap naskah pengganti harus menyertakan penilaian aset visual: apa yang sudah cukup, apa yang perlu ditambah, dan apa yang sengaja tidak ditambah beserta alasannya.
- Sitasi dan teori di BAB IV boleh dikurangi selama sudah ada di BAB II/BAB III.
- Isi laporan harus dicek konsistensinya terhadap kode di `D:\Kulyeah\SKRIPSI\project\lensalabel`.
- Jangan mengarang hasil, angka, waktu deployment, atau hasil wawancara.
- Istilah asing dimiringkan. Nama teknologi (EasyOCR, OpenCV, FastAPI, React, Render, Modal, Neon) tidak dimiringkan.
- Kategori verdict selalu ditulis lengkap: **Aman**, **Perlu Perhatian**, **Hindari**, **Perlu Verifikasi**, **Tidak Terbaca**.
- Hindari em dash dalam prosa akademik.

---

## 3. Temuan verifikasi yang mengubah segalanya

### 3.1 Ketidakselarasan nama

Evaluasi tingkat bahan membandingkan `standard_name` secara **persis**. Sebanyak **150 anotasi** di GT evaluasi memakai nama yang tidak ada di KB v2:

| Nama GT lama | Jumlah | Target KB v2 | Status |
|---|---:|---|---|
| Gula pasir murni | 129 | v2-147 | Tidak ambigu (alias persis) |
| Sukrosa | 7 | v2-147 | Tidak ambigu (alias persis) |
| Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum | 7 | v2-147 | Tidak ambigu (alias persis) |
| Natrium karboksimetil selulosa (Na-CMC) | 3 | v2-206 | Tidak ambigu (alias persis) |
| Metil selulosa / Karboksi metil selulosa | 1 | v2-206 | Tidak ambigu (alias persis) |
| Margarin (mengandung whey/susu) | 2 | v2-028b | Keputusan ahli |
| Licorice | 1 | dikecualikan | Keputusan ahli |

### 3.2 Ketidakselarasan kategori

Sebanyak **382 anotasi** memakai kategori lama yang berbeda dari KB v2. Rincian arah perubahan:

| Perubahan | Jumlah |
|---|---:|
| perhatian → aman | 247 |
| hindari → perhatian | 82 |
| aman → perhatian | 45 |
| perhatian → hindari | 8 |

Contoh berdampak besar: MSG dan Dinatrium Inosinat turun ke Aman; TBHQ, Natrium Benzoat, Tartrazin, BHA, BHT, Aspartam turun ke Perlu Perhatian; Stevia, Sukralosa, Sorbitol naik ke Perlu Perhatian.

**Keputusan pengguna:** KB v2 menjadi acuan kategori final untuk evaluasi.

### 3.3 Keputusan ahli gizi

Workbook validasi diisi ahli dengan hasil:

- **MAP-01** `datar_022.jpeg`, Margarin → **v2-028b** (Margarin komposisi tidak dirinci, Perlu Perhatian). Alasan ahli: label hanya menyebut antioksidan BHA dan pewarna beta karoten; susu berasal dari bahan lain, bukan margarin.
- **MAP-02** `datar_027.jpeg`, Margarin → **v2-028b**. Alasan serupa: susu hanya ada pada butiran cokelat dan keju, bukan margarin.
- **MAP-03** `melengkung_096.jpeg`, Licorice → **TIDAK_DAPAT_DITETAPKAN**. Label hanya berbunyi "PERISA ALAMI LICORICE", tidak mendukung ekstrak licorice maupun permen licorice. Ahli mencatat perlu keputusan terpisah apakah perisa licorice butuh entri KB sendiri.

**Keputusan pengguna untuk MAP-03:** keluarkan anotasi Licorice dari GT evaluasi, catat alasannya. Tidak menambah entri KB baru.

---

## 4. Artefak yang sudah dibuat

### 4.1 Ground truth baru

`evaluation/ground_truth/evaluation_gt_kb_v2_final.json`

- 160 foto, **1.483 item** (sebelumnya 1.490; 7 berkurang karena penggabungan entri gula/selulosa dan 1 pengecualian Licorice).
- Seluruh nama kanonis KB v2, seluruh kategori cocok dengan KB v2, validator 0 error.
- Distribusi kategori: Aman 932, Perlu Perhatian 358, Hindari 193.
- Distribusi verdict GT produk: **Hindari 91, Perlu Perhatian 57, Aman 12** (sebelumnya 116 / 39 / 5).
- Verdict GT berubah pada **38 dari 160 foto**: 27 Hindari→Perlu Perhatian, 8 Perlu Perhatian→Aman, 2 Perlu Perhatian→Hindari, 1 Aman→Perlu Perhatian.

**GT lama tidak diubah** (`evaluation/ground_truth/evaluation_gt_final.json` tetap ada sebagai baseline historis).

### 4.2 Laporan pemetaan

`evaluation/results/gt_v2_alignment/evaluation_gt_kb_v2_alignment_report.json`

Memuat 531 event pemetaan, rincian pengecualian Licorice berikuti alasan ahli, hitungan perubahan kategori, serta SHA-256 GT sumber dan KB v2.

### 4.3 Workbook validasi ahli (sudah terisi)

`evaluation/results/gt_v2_alignment/validasi_pemetaan_gt_ke_kb_v2.xlsx`

Berisi sheet `petunjuk`, `keputusan_ahli` (terisi), `MAP-01` sampai `MAP-03`, `pemetaan_otomatis`, dan `provenance`. Simpan sebagai bukti audit.

### 4.4 Skrip baru

| Berkas | Fungsi |
|---|---|
| `evaluation/build_gt_alignment_review_packet.py` | Membuat workbook validasi ahli |
| `evaluation/validate_gt_kb_alignment.py` | Memeriksa GT terhadap KB v2 (nama + kategori) |
| `evaluation/build_eval_gt_kb_v2_aligned.py` | Membangun GT kanonis KB v2 dari GT lama + keputusan ahli |
| `evaluation/freeze_evaluation_config_v2.py` | Membuat freeze v2 tanpa menimpa v1 |
| `evaluation/tests/test_gt_kb_alignment.py` | Test validator |

### 4.5 Konfigurasi beku v2

`evaluation/config_frozen_v2.json` (+ sidecar `.sha256`), status `frozen`:

- `max_ocr_width`: **1500** piksel
- `adaptive_threshold`: **false**
- `threshold`: **75**
- `evaluation_gt_path`: `evaluation/ground_truth/evaluation_gt_kb_v2_final.json`
- F1 kalibrasi: 0,7618; precision 0,8503; recall 0,6899; recall Hindari 0,6053

Freeze v1 **tidak disentuh** dan hash sidecar-nya masih cocok.

### 4.6 Hasil kalibrasi ulang (40 foto, GT kalibrasi yang sudah selaras KB v2)

| Konfigurasi | Threshold | Precision | Recall | F1 | Recall Hindari | OCR s/foto |
|---|---:|---:|---:|---:|---:|---:|
| 2000/OFF | 70 | 0,7871 | 0,7545 | 0,7704 | 0,6316 | 3,922 |
| 1500/OFF | 75 | 0,8503 | 0,6899 | **0,7618** | 0,6053 | 2,667 |
| 1000/OFF | 70 | 0,8084 | 0,6977 | 0,7490 | 0,6053 | 1,994 |
| 2000/ON | 65 | 0,6939 | 0,5917 | 0,6388 | 0,5263 | 3,989 |
| 1500/ON | 70 | 0,7799 | 0,5401 | 0,6382 | 0,5000 | 2,723 |
| 1000/ON | 70 | 0,7765 | 0,5297 | 0,6298 | 0,6053 | 1,634 |

**Konfigurasi terpilih tetap 1500/OFF threshold 75**, bukan 2000/OFF. Alasannya: F1 tertinggi adalah 2000/OFF 0,7704, tetapi selisihnya dengan 1500/OFF 0,7618 hanya 0,0086, di bawah batas 0,01, sehingga aturan tie-break memilih waktu OCR lebih rendah. Ini penting: jangan menyimpulkan 2000/OFF terpilih hanya dari F1 maksimum.

Catatan: perhitungan threshold di dalam satu konfigurasi memakai aturan F1 maksimum dengan tie-break recall Hindari bila selisih di bawah 0,01. Untuk 2000/OFF, aturan itu memilih threshold 70, bukan 75.

Hasil tersimpan di `evaluation/results/grid_width_*_postfix_v2/`, masing-masing berisi `grid_summary.csv`, `grid_detail.csv`, `bootstrap_ci.csv`, dan `provisional_run_metadata.json`.

### 4.7 Gambar untuk 4.4.4

`C:\Users\INFINIX\tmp_work\gambar_f1_kalibrasi.png` dibuat dari data **lama** (GT v2.2 pra-penyelarasan). **Gambar ini harus dibuat ulang** dari grid `postfix_v2` sebelum dipakai di laporan.

---

## 5. Yang belum selesai

### 5.1 OCR ulang 160 foto (wajib, belum dijalankan)

Alasannya: GT baru, kode pasca-perbaikan, dan konfigurasi beku v2. Cache OCR lama tidak boleh dipakai.

Perintah di lingkungan Colab (bundle v2 sudah siap, lihat 5.2):

```powershell
python evaluation/colab_evaluate_160_ocr.py --config config_frozen_v2.json
```

Catatan teknis:

- Skrip sudah mendukung `--config`. Tanpa argumen itu, skrip memakai v1.
- Skrip memverifikasi sidecar hash konfigurasi, KB, dan GT evaluasi sebelum jalan.
- Butuh lingkungan dengan EasyOCR dan idealnya GPU (Colab).
- Output: `evaluation/results/evaluation_ocr/evaluation_ocr_160.csv` (akan menimpa nama berkas lama; cadangkan dulu bila ingin membandingkan).

### 5.2 Bundle Colab (SUDAH SELESAI)

Commit dan tag yang dibuat:

- `8a314d7` — kode pasca-perbaikan, GT kanonis KB v2, validator, builder GT, freeze v2.
- `2921d06` — `config_frozen_v2.json`, sidecar `.sha256`, dan bundler yang mendukung `--config`.
- Tag anotasi: **`eval-freeze-v2`** (v1 tetap ada sebagai baseline historis).

Bundle siap pakai:

```
evaluation/results/lensalabel_eval_freeze_v2_colab.zip
```

Verifikasi yang sudah dilakukan pada bundle:

- 467 entri, 307 berkas terlacak, 160 foto evaluasi terverifikasi SHA-256 terhadap `photo_manifest.csv`.
- `zipfile.testzip()` bersih (tidak ada entri rusak).
- `evaluation/config_frozen_v2.json` di dalam bundle cocok dengan sidecar hash-nya.
- Nilai di dalam bundle: `frozen`, 1500 px, adaptive `False`, threshold 75.
- GT baru `evaluation/ground_truth/evaluation_gt_kb_v2_final.json` ikut di dalam bundle.
- Ukuran ± 449 MB.

Perintah bundler untuk reproduksi:

```powershell
python evaluation/build_colab_eval_bundle.py --tag eval-freeze-v2 --config config_frozen_v2.json --output evaluation/results/lensalabel_eval_freeze_v2_colab.zip
```

Catatan: berkas zip berada di `evaluation/results/` yang di-ignore git, jadi bundle tidak ikut commit. Simpan salinannya di tempat aman sebelum mengunggah ke Colab.

### 5.3 Evaluasi dan regenerasi aset

Setelah OCR baru tersedia:

```powershell
python evaluation/run_evaluate_160_parallel.py verify-calibration --workers N
python evaluation/run_evaluate_160_parallel.py run-evaluation --workers N
python evaluation/analyze_post_evaluation.py
python evaluation/package_final_evaluation_assets.py
```

Kemungkinan perlu penyesuaian karena skrip-skrip ini masih membaca `config_frozen.json` v1.

### 5.4 Pembaruan laporan Word

Belum satu pun angka BAB IV diperbarui. Subbab yang wajib berubah setelah evaluasi baru:

- **4.4.4**: Tabel 4.9, grafik F1 kalibrasi, alasan pemilihan konfigurasi, Tabel 4.10.
- **4.5.1**: CER/WER bila OCR berubah.
- **4.5.2**: Tabel 4.13, Tabel 4.14, grafik F1 kategori.
- **4.5.3**: Tabel 4.15–4.17, confusion matrix, baseline mayoritas, kappa.
- **4.5.4**: Tabel 4.18–4.21, grafik fallback.
- **4.5.5**: Tabel 4.22–4.23, grafik penyebab kesalahan.
- Abstrak, BAB V, dan lampiran yang mengutip angka.

Perlu juga ditambahkan satu paragraf transparan bahwa baseline akhir memakai konfigurasi beku v2 setelah penyelarasan GT ke KB v2.

---

## 6. Peringatan penting

1. **Jangan mencampur artefak lama dan baru.** Cache prediksi `evaluation_predictions_cache.jsonl` menyimpan metadata provenance; cache lama akan ditolak bila konfigurasi berubah.
2. **Angka majority baseline berubah.** GT Hindari turun dari 72,5% menjadi 56,9% dari 160 foto. Narasi "selisih akurasi hanya 0,6 poin persentase" di 4.5.3 tidak lagi berlaku.
3. **Jangan mengklaim Cohen's kappa sebagai kesepakatan ahli.** Kappa 0,437 adalah kesepakatan sistem terhadap ground truth produk, bukan antar-ahli.
4. **Validasi KB hanya oleh satu ahli gizi.** Jangan mengklaim CVR/CVI atau kesepakatan antar-ahli.
5. **Hasil wawancara ahli terhadap output sistem belum selesai.** Paket 16 produk sudah disiapkan di `evaluation/results/expert_interview/`, tetapi belum ada respons.
6. **Folder `evaluation/results/evaluation_ocr/`** berisi hasil evaluasi ulang 29 Oktober pasca-perbaikan bug (sebelum penyelarasan GT). Jangan dianggap final.
7. **Dokumen Word laporan** adalah `LAPORAN TUGAS AKHI1(6).docx` di `D:\Kulyeah\SKRIPSI\SKRIPSI gw\skripsi\`. Halaman DAFTAR PUSTAKA masih kosong; perlu Ctrl+A lalu F9 dan update bibliografi Mendeley/Zotero.

---

## 7. Status revisi naskah BAB IV

| Subbab | Status |
|---|---|
| 4.3.2 Transkripsi dan Ground Truth | Sudah diterapkan (screenshot `transcripts.csv` jadi Gambar 4.6, R1–R4 dipindah ke BAB III) |
| 4.3.3 Pembagian Subset | Sudah diterapkan |
| 4.3.4 Pra-pemrosesan Citra | Sudah diterapkan (termasuk gambar perbandingan adaptive thresholding) |
| 4.3.5 Penyaringan Komposisi dan Tokenisasi | Sudah diterapkan |
| 4.4.1 Optical Character Recognition | Sudah diterapkan |
| 4.4.2 Rule-Based Fuzzy String Matching | Sudah diterapkan |
| 4.4.3 Rule-Based Classification dan Product Verdict | Sudah diterapkan (tanpa aturan override di Tabel 4.8) |
| 4.4.4 Kalibrasi dan Frozen Configuration | Draf diserahkan; **angka akan berubah lagi** setelah GT baru |
| 4.5.1 Evaluasi OCR | Draf diserahkan, menunggu penerapan |
| 4.5.2 Evaluasi Identifikasi Bahan | Draf diserahkan + angka P/R per kondisi ditemukan; menunggu penerapan |
| 4.5.3 Evaluasi Kategori dan Product Verdict | Suntingan terarah diberikan; **angka akan berubah total** |
| 4.5.4 Evaluasi Mekanisme Fallback | Suntingan + gambar baru diserahkan; **angka akan berubah** |
| 4.5.5 Analisis Kesalahan | Suntingan diberikan; **angka akan berubah** |
| 4.5.6 Evaluasi Ahli | Belum ditulis; menunggu wawancara |
| 4.6 Deployment | Belum diperiksa mendalam; diagram harus Render → Modal → Neon |

---

## 8. Fakta teknis yang sudah terverifikasi

- Preprocessing: grayscale → Gaussian blur 3×3 → CLAHE (clipLimit 2,0; tile 8×8) → deskew (lewati bila |sudut| < 0,5°). Downscale terpisah di modul OCR.
- Matcher: Levenshtein + Jaro-Winkler + Dice bigram, bobot 1/3 masing-masing, penalti panjang eksponen 0,8, threshold 75, jendela n−1/n/n+1 kata, 14 blocked pairs.
- Verdict: urutan cek kode `tidak_terbaca → hindari → perhatian → perlu_verifikasi → aman`. Tabel 4.8 disusun menurut prioritas risiko, bukan urutan kode; hasilnya sama karena kondisi saling eksklusif.
- Override `opening_found` → Aman diturunkan ke Perlu Verifikasi **hanya ada di `routes_identify.py`** dan **tidak aktif dalam evaluasi offline**.
- Deduplikasi `standard_name` terjadi sebelum verdict ditetapkan.
- Kalibrasi: 40 foto; evaluasi: 160 foto; seed 42; split tersimpan di `evaluation/splits/`.
- GT kalibrasi (`calibration_ingredients_gt_v2_2.json`) sudah selaras KB v2 sejak awal, 387 item, 0 masalah.

---

## 9. Langkah berikutnya yang disarankan

1. Cadangkan `evaluation/results/evaluation_ocr/` sebelum OCR ulang.
2. Jalankan OCR 160 foto dengan `--config config_frozen_v2.json` di Colab/GPU.
3. Simpan CSV hasil dan catat environment (EasyOCR, torch, OpenCV).
4. Sesuaikan `run_evaluate_160_parallel.py`, `analyze_post_evaluation.py`, dan `package_final_evaluation_assets.py` agar menerima konfigurasi v2.
5. Jalankan evaluasi, lalu bandingkan angka baru dengan angka lama secara eksplisit untuk keperluan pembahasan perubahan.
6. Regenerasi semua tabel dan gambar BAB IV.
7. Perbarui laporan Word dan tambahkan catatan metodologis tentang penyelarasan GT.
