# Runbook Colab: ablation OCR kalibrasi

Eksperimen ini hanya memakai 40 foto dalam `evaluation/splits/calibration_set.csv`. Jangan unggah atau menjalankan manifest evaluasi 160 foto.

## Berkas yang diunggah

Unggah satu ZIP dengan struktur project minimal berikut:

- `evaluation/colab_calibration_ocr_ablation.py`
- `evaluation/splits/calibration_set.csv`
- `evaluation/requirements-colab.txt`
- `dataset/ground_truth/transcripts.csv`
- 40 foto kalibrasi pada `dataset/raw_photos/datar/` dan `dataset/raw_photos/melengkung/`, sesuai nama yang tercantum di manifest.
- Modul project yang diimpor skrip: `backend/app/ocr/reader.py`, `backend/app/preprocessing/pipeline.py`, serta `backend/app` package files (`__init__.py`).

Cache OCR **tidak diperlukan** untuk ablation ini: setiap konfigurasi harus mengulang OCR pada foto yang sama dengan preprocessing dan lebar OCR berbeda. Cache yang ada hanya dipakai untuk grid search matcher, bukan eksperimen OCR.

## Urutan sel di Colab

1. Pilih **Runtime > Change runtime type > T4 GPU**, simpan, lalu mulai sesi baru. Unggah dan ekstrak ZIP project yang terbaru ke `/content/lensalabel`.
2. Hapus semua distribusi OpenCV yang berbagi namespace `cv2`:

   ```python
   %pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python
   ```

3. Pasang satu distribusi OpenCV yang ditetapkan:

   ```python
   %pip install opencv-python-headless==5.0.0.93
   ```

4. Pasang dependensi eksperimen. `requirements-colab.txt` mematok paket headless ke versi yang sama dan tidak seharusnya menambah dua distribusi OpenCV lainnya:

   ```python
   %pip install -r /content/lensalabel/evaluation/requirements-colab.txt
   ```

5. Setelah instalasi selesai, pilih **Runtime > Restart session**. Pada sel pertama setelah restart, pastikan runtime dan modul yang diimpor benar:

   ```python
   import cv2
   import torch
   import easyocr
   from importlib.metadata import version
   print("CUDA:", torch.cuda.is_available())
   print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "tidak tersedia")
   print("EasyOCR:", version("easyocr"))
   print("Torch:", torch.__version__)
   print(cv2.__version__)
   print(cv2.__file__)
   print("OpenCV headless:", version("opencv-python-headless"))
   ```

   Hasil yang diharapkan: versi runtime `5.0.0`, path `cv2` berada di `/usr/local/lib/python3.13/dist-packages/cv2/`, dan hanya paket headless terpasang. Skrip ablation juga menolak lebih dari satu distribusi OpenCV. Pastikan `CUDA: True`.
6. Aktifkan pemakaian GPU oleh EasyOCR lalu jalankan enam konfigurasi ablation:

   ```bash
   %cd /content/lensalabel
   %env EASYOCR_GPU=1
   !python evaluation/colab_calibration_ocr_ablation.py
   ```

   Skrip memverifikasi manifest 40 foto unik dan semua transkrip/foto tersedia. Ia menjalankan enam konfigurasi: lebar OCR 1000, 1500, 2000, masing-masing dengan adaptive threshold OFF dan ON. Hasilnya mencatat CER/WER teks penuh, komposisi ekstraksi, dan OCR lokal.

7. Unduh tiga berkas berikut dari `evaluation/results/calibration_ocr_ablation/`:

- `ocr_ablation_summary.csv`
- `ocr_ablation_detail.csv`
- `environment_versions.json`

Skrip ini tidak menyimpan ulang foto atau mengubah transcript, dataset, matcher, maupun konfigurasi produksi.
