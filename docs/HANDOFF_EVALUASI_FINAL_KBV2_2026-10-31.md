# Handoff Konteks: LensaLabel — Hasil Evaluasi Final KB v2 (31 Oktober 2026)

Dokumen ini adalah konteks terbaru untuk melanjutkan revisi laporan tugas akhir LensaLabel di AI atau sesi lain. Dokumen ini **menggantikan** handoff sebelumnya karena seluruh pipeline evaluasi pasca-penyelarasan sudah selesai dijalankan dan angka final sudah tersedia.

Bacalah sepenuhnya sebelum bertindak. Angka pada BAB IV yang masih memakai hasil lama harus diganti dengan angka di dokumen ini.

---

## 1. Status terbaru

**Selesai:** penyelarasan ground truth ke KB v2, kalibrasi ulang, konfigurasi beku v2, OCR ulang 160 foto, evaluasi akhir, regenerasi aset BAB IV.

**Belum:** pembaruan angka pada dokumen Word, catatan metodologis, abstrak, dan BAB V.

---

## 2. Mengapa angka lama di laporan tidak valid

Angka yang saat ini ada di laporan (F1 bahan 0,723; F1 kategori 0,911; accuracy 0,731; kappa 0,437) berasal dari ground truth yang tidak selaras dengan KB v2 dan kode yang mengandung bug deskew.

1. **GT tidak selaras**: 150 anotasi memakai `standard_name` lama yang tidak ada di KB v2 (terutama gula), dan 382 anotasi memakai kategori lama yang berbeda dari KB v2. Hasilnya, bahan yang diprediksi benar secara semantik tercatat sebagai FP dan FN.
2. **Bug deskew**: perbaikan sudut deskew di commit `8a314d7` hanya memetakan `angle > 45`. Pada OpenCV 5 (Colab), `minAreaRect` mengembalikan rentang [-90, 0), sehingga foto tegak dengan sudut mentah -90 dirotasi -90 derajat. Label berdiri vertikal dan OCR gagal. Diperbaiki dengan normalisasi sudut ke (-45, 45] sehingga foto tegak tidak dirotasi.
3. **Kode yang di-deploy** mengandung perbaikan tokenizer dan matcher yang belum tercermin pada hasil lama.

Karena itu evaluasi final dihitung ulang pada konfigurasi beku v2.

---

## 3. Keputusan metodologis yang sudah diambil pengguna

1. **KB v2 sebagai acuan kategori final.** 382 anotasi dengan kategori berbeda diselaraskan ke kategori KB v2 yang sudah divalidasi ahli.
2. **Dua kasus nama ambigu divalidasi ahli gizi.** Hasilnya:
   - `datar_022.jpeg`, Margarin → **v2-028b** (Margarin komposisi tidak dirinci, Perlu Perhatian).
   - `datar_027.jpeg`, Margarin → **v2-028b**.
   - `melengkung_096.jpeg`, Licorice → **TIDAK_DAPAT_DITETAPKAN**; anotasi Licorice dikeluarkan dari GT dengan catatan ahli sebagai bukti. Keputusan pengguna: keluarkan, tidak menambah entri KB baru.
3. **Lima nama lain dipetakan otomatis** karena alias KB v2 memuat nama GT lama secara persis dan kategorinya sama: tiga gula → v2-147, dua selulosa → v2-206.

GT evaluasi baru: `evaluation/ground_truth/evaluation_gt_kb_v2_final.json`, 160 foto, **1.483 item** (sebelumnya 1.490). Verdict GT produk berubah menjadi **Hindari 91, Perlu Perhatian 57, Aman 12** (sebelumnya 116 / 39 / 5). Verdict berubah pada 38 dari 160 foto.

---

## 4. Konfigurasi beku final (v2)

| Parameter | Nilai |
|---|---|
| Konfigurasi terpilih | 1500 px / adaptive OFF / threshold 75 |
| F1 kalibrasi | 0,7618 |
| Precision / Recall kalibrasi | 0,8503 / 0,6899 |
| Recall Hindari kalibrasi | 0,6053 |
| Bobot matcher | 1/3 Levenshtein + 1/3 Jaro-Winkler + 1/3 Dice bigram |
| Eksponen penalti panjang | 0,8 |
| Preprocessing | grayscale → Gaussian blur → CLAHE → deskew |
| GT evaluasi | `evaluation/ground_truth/evaluation_gt_kb_v2_final.json` |

Konfigurasi terpilih **tetap** 1500/OFF threshold 75, sama seperti v1. Yang berubah adalah GT-nya. Alasan tie-break: F1 2000/OFF 0,7704 vs 1500/OFF 0,7618, selisih 0,0086 < 0,01 sehingga waktu OCR lebih rendah (2,667 vs 3,922 detik/foto) dipilih. **Jangan salah menyimpulkan 2000/OFF terpilih hanya karena F1-nya lebih tinggi.**

Freeze tertulis di `evaluation/config_frozen_v2.json` beserta sidecar. Tag git: `eval-freeze-v2`. Bundle Colab: `evaluation/results/lensalabel_eval_freeze_v2_colab.zip` (449 MB, 160 foto terverifikasi, mengandung perbaikan deskew).

---

## 5. Hasil evaluasi final (v2)

### 5.1 Identifikasi bahan (Tabel 4.13)

| Metrik | Nilai | CI 95% |
|---|---|---|
| Precision | 0,848 | 0,823–0,869 |
| Recall | 0,778 | 0,747–0,809 |
| F1-score | 0,812 | 0,789–0,833 |

Per kondisi: Datar P 0,868 / R 0,813 / F1 0,839; Melengkung P 0,822 / R 0,735 / F1 0,776. F1 per kategori bahan: Aman 0,838; Perlu Perhatian 0,736; Hindari 0,821.

### 5.2 Kategori (keberadaan) (Tabel 4.15)

| Metrik | Nilai | CI 95% |
|---|---|---|
| Precision | 0,948 | 0,923–0,970 |
| Recall | 0,945 | 0,916–0,969 |
| F1-score | 0,947 | 0,927–0,962 |

F1 per kelas: Aman 0,991; Perlu Perhatian 0,891; Hindari 0,951.

### 5.3 Verdict produk (Tabel 4.17)

| Metrik | Nilai | CI 95% |
|---|---|---|
| Accuracy | 0,888 | 0,838–0,931 |
| Macro-F1 | 0,610 | (dihitung dari confusion) |
| Cohen's kappa | 0,783 | (dihitung dari confusion) |
| Recall Hindari | 0,967 | 0,924–1,000 |

Majority baseline accuracy: 0,569. Kelas Aman tetap 0,000 karena sistem tidak memprediksi satu pun dari 5 produk Aman; itu yang menahan macro-F1 di 0,610.

### 5.4 Confusion matrix verdict (Gambar yang menggantikan matriks lama)

Baris = GT, kolom = prediksi (Aman / Perlu Perhatian / Hindari):

| | Aman | Perlu Perhatian | Hindari |
|---|---|---|---|
| **Aman (5)** | 0 | 9 | 3 |
| **Perlu Perhatian (57)** | 0 | 54 | 3 |
| **Hindari (91)** | 0 | 3 | 88 |

Tidak ada GT Hindari yang diprediksi Aman. Distribusi status mentah: Aman 0, Perlu Perhatian 55, Hindari 94, Perlu Verifikasi 11, Tidak Terbaca 0.

### 5.5 Perbandingan lama → baru

| Tingkat | v1 | **v2** |
|---|---|---|
| Ingredient F1 | 0,723 | **0,812** |
| Kategori F1 | 0,911 | **0,947** |
| Accuracy | 0,731 | **0,888** |
| Macro-F1 | 0,552 | **0,610** |
| Cohen's kappa | 0,437 | **0,783** |
| Recall Hindari | 0,741 | **0,967** |

---

## 6. Gambar siap pakai

| Berkas | Untuk |
|---|---|
| `C:\Users\INFINIX\tmp_work\gambar_f1_kalibrasi_v2.png` | Grafik F1 vs threshold konfigurasi terpilih + pembanding 2000/OFF, menandai 1500/OFF t=75 (F1 0,7618) |
| `C:\Users\INFINIX\tmp_work\gambar_confusion_verdict_v2.png` | Confusion matrix verdict final |
| `evaluation/results/chapter4/` | Paket tabel, workbook, dan gambar resmi dari runner |
| `evaluation/results/chapter4_assets_final.zip` | Bundle aset final |

Catatan: `gambar_4_11_confusion_verdict_160.png` di `chapter4/` dihasilkan runner resmi. Gambar confusion di `tmp_work` adalah versi presentasi bersih dengan label "Perlu Perhatian" lengkap; pilih salah satu secara konsisten.

---

## 7. Artefak penting dan path

| Item | Path |
|---|---|
| GT final | `evaluation/ground_truth/evaluation_gt_kb_v2_final.json` |
| Laporan pemetaan | `evaluation/results/gt_v2_alignment/evaluation_gt_kb_v2_alignment_report.json` |
| Workbook ahli (terisi) | `evaluation/results/gt_v2_alignment/validasi_pemetaan_gt_ke_kb_v2.xlsx` |
| OCR baru | `evaluation/results/evaluation_ocr/evaluation_ocr_160.csv` |
| Prediksi & metrik | `evaluation/results/evaluation_ocr/` dan `evaluation/results/post_evaluation/` |
| Kalibrasi grid baru | `evaluation/results/grid_width_*_postfix_v2/` |
| Artefak lama (diarsipkan) | `evaluation/results/evaluation_ocr_baseline_v1/` |
| Bundle Colab v2 | `evaluation/results/lensalabel_eval_freeze_v2_colab.zip` |
| Freeze v2 | `evaluation/config_frozen_v2.json` + `.sha256` |

---

## 8. Yang belum selesai

1. **Pembaruan BAB IV** di `LAPORAN TUGAS AKHI1(6).docx` memakai angka di bagian 5. Subbab yang berubah: 4.4.4, 4.5.1, 4.5.2, 4.5.3, 4.5.4, 4.5.5. Confusion matrix lama diganti dengan matriks di 5.4.
2. **Catatan metodologis** satu paragraf di BAB IV bahwa baseline akhir memakai konfigurasi beku v2 setelah penyelarasan GT ke KB v2 dan perbaikan guard deskew.
3. **Abstrak dan BAB V** yang mengutip angka lama.
4. **Halaman DAFTAR PUSTAKA** masih kosong; perlu Ctrl+A lalu F9 dan update bibliografi Mendeley/Zotero.
5. **Hasil wawancara ahli** terhadap output sistem (16 produk) belum tersedia; paket sudah disiapkan di `evaluation/results/expert_interview/`.

---

## 9. Perintah untuk mereproduksi evaluasi

```powershell
# 1. OCR 160 foto (di Colab/GPU)
python evaluation/colab_evaluate_160_ocr.py --config config_frozen_v2.json

# 2. Gate kalibrasi lalu evaluasi
python evaluation/run_evaluate_160_parallel.py verify-calibration --workers N --config config_frozen_v2.json
python evaluation/run_evaluate_160_parallel.py run-evaluation --workers N --config config_frozen_v2.json

# 3. Analisis pasca-evaluasi dan paket aset
python evaluation/analyze_post_evaluation.py
python evaluation/package_final_evaluation_assets.py --config config_frozen_v2.json
```

Catatan: runner menolak cache lama yang provenance-nya tidak cocok. Cache prediksi harus dibuat ulang setiap kali konfigurasi berubah.

---

## 10. Aturan kerja untuk AI penerima

- Bahasa Indonesia akademik, lugas, tidak bertele-tele.
- Jangan mengarang hasil, angka, waktu deployment, atau hasil wawancara.
- Angka yang boleh dipakai di BAB IV hanya angka di bagian 5 dokumen ini; jangan mengambil angka lama dari laporan.
- Istilah asing dimiringkan. Nama teknologi (EasyOCR, OpenCV, FastAPI, React, Render, Modal, Neon) tidak dimiringkan.
- Kategori verdict selalu ditulis lengkap: Aman, Perlu Perhatian, Hindari, Perlu Verifikasi, Tidak Terbaca.
- Jangan menyebut Cohen's kappa 0,783 sebagai kesepakatan ahli; itu kesepakatan sistem terhadap ground truth produk.
- Validasi knowledge base hanya oleh satu ahli gizi; jangan mengklaim CVR/CVI atau kesepakatan antar-ahli.
- Hindari em dash dalam prosa akademik.
- Untuk setiap subbab yang direvisi, sertakan penilaian aset visual: apa yang sudah cukup, apa yang perlu ditambah, dan apa yang sengaja tidak ditambah beserta alasannya.
