# Runbook Colab untuk OCR evaluasi 160 foto

Bundel hanya dibuat setelah `eval-freeze-v1` tersedia. Sebelum konfigurasi
dibekukan, jangan jalankan OCR evaluasi atau hitung metrik.

## Bekukan konfigurasi

Setelah konfigurasi ditinjau dan disetujui, dari root repo jalankan:

```powershell
Set-Location D:\Kulyeah\SKRIPSI\project\lensalabel
.\backend\.venv\Scripts\python.exe .\evaluation\freeze_evaluation_config.py --confirm
```

Skrip memakai HEAD saat ini jika seluruh input sudah dikomit. Ia hanya
mengganti tag lokal `eval-freeze-v1` bila tag lama masih menunjuk ke commit
leluhur dengan config berstatus `draft` dan belum memiliki sidecar hash. Tag
yang sudah frozen atau bukan leluhur HEAD ditolak. Jangan membuat atau
memindahkan tag secara manual.

Freeze mencatat commit input bila masih ada perubahan relevan, lalu membuat
commit freeze, `evaluation/config_frozen.sha256`, memperbarui
`dataset/freeze_input_hashes.csv`, dan menempatkan tag pada commit freeze.
Verifikasi status config, tag, dan hash sebelum membuat bundel:

```powershell
git status --short --branch
git show eval-freeze-v1:evaluation/config_frozen.json
git show eval-freeze-v1:evaluation/config_frozen.sha256
$expected = (Get-Content .\evaluation\config_frozen.sha256).Split(' ')[0]
$actual = (Get-FileHash .\evaluation\config_frozen.json -Algorithm SHA256).Hash.ToLower()
if ($expected -ne $actual) { throw 'Hash config tidak cocok' }
git tag --points-at HEAD
```

## Buat dan unggah bundel

Di komputer lokal, dari root repo:

```powershell
backend/.venv/Scripts/python.exe evaluation/build_colab_eval_bundle.py
```

Skrip mengambil file terlacak dari tag menggunakan `git archive`, lalu
menambahkan tepat 160 foto split evaluasi. Setiap foto diperiksa terhadap
`dataset/photo_manifest.csv` berdasarkan kondisi, ukuran, dan SHA-256.
Sebelum membuat ZIP, skrip juga memastikan tag berstatus `frozen` dan hash
`config_frozen.json` cocok dengan sidecar `evaluation/config_frozen.sha256`.
Bundel keluar di `evaluation/results/lensalabel_eval_freeze_v1_colab.zip`.
Unggah ZIP itu ke Google Drive atau langsung ke sesi Colab.

## Siapkan runtime

Pilih **Runtime → Change runtime type → T4 GPU**, lalu jalankan:

```python
from google.colab import drive
drive.mount('/content/drive')
!unzip -q /content/drive/MyDrive/lensalabel_eval_freeze_v1_colab.zip -d /content/lensalabel
%cd /content/lensalabel
!pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python
!pip install -r evaluation/requirements-colab.txt
```

Restart runtime setelah instalasi OpenCV bila diminta. Pastikan runtime GPU:

```python
import torch, cv2
from importlib.metadata import version, PackageNotFoundError
print('CUDA:', torch.cuda.is_available())
print('EasyOCR:', version('easyocr'))
print('Torch:', torch.__version__)
print('OpenCV:', cv2.__version__, cv2.__file__)
```

## Jalankan OCR dan unduh hasil

```python
!python evaluation/colab_evaluate_160_ocr.py
```

Skrip menolak status config yang bukan `frozen`, SHA-256 config/KB/GT yang
berbeda, atau instalasi dengan lebih dari satu distribusi OpenCV. Skrip
mencetak versi EasyOCR, Torch, `cv2.__version__`, dan `cv2.__file__` sebelum
memproses gambar. Ia hanya menyimpan teks OCR dan durasi per foto; tidak
menghitung metrik.

Unduh `evaluation/results/evaluation_ocr/evaluation_ocr_160.csv`. Setelah
file ditinjau dan ditempatkan di repo lokal, metrik dihitung terpisah dengan
`evaluation/evaluate_160_metrics.py`.
