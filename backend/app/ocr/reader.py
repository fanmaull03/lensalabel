"""Tahap 3 - Integrasi EasyOCR.

Reader di-load SEKALI (module-level singleton, lazy). Loading model paling
berat di CPU, jadi jangan pernah inisialisasi ulang per panggilan.

Downscale ke lebar maks 1000px di modul ini adalah optimasi performa OCR,
BUKAN bagian dari 5 tahap preprocessing resmi (lihat preprocessing/pipeline.py
yang urutannya fix sesuai proposal). Sengaja dipisah di sini.
"""

from __future__ import annotations

import cv2
import numpy as np

# Knob: batas lebar sebelum readtext. Naik dari 1000 -> 2000 berdasarkan
# eksperimen ablasi (resolution_ablation_colab_summary.txt): 2000px jauh lebih
# baik dari 1000px, sementara resolusi penuh 12MP tidak menambah kualitas
# signifikan tapi makan 71.4 detik/foto. Kombinasi preprocessing (blur/CLAHE)
# di 2000px tidak berpengaruh signifikan, jadi pipeline preprocessing tetap
# 5 tahap penuh sesuai proposal.
MAX_OCR_WIDTH = 2000

_reader = None  # singleton, diisi saat pertama kali dibutuhkan


def get_reader():
    """Kembalikan instance EasyOCR tunggal (id+en, CPU-only). Lazy-loaded."""
    global _reader
    if _reader is None:
        import easyocr  # import di sini supaya modul lain tak ikut nunggu load model

        _reader = easyocr.Reader(["id", "en"], gpu=False)
    return _reader


def _downscale(image: np.ndarray, max_width: int | None) -> np.ndarray:
    """Perkecil ke lebar max_width kalau kelebihan, jaga aspect ratio.

    max_width=None berarti pakai ukuran asli (tanpa downscale).
    """
    w = image.shape[1]
    if max_width is None or w <= max_width:
        return image
    scale = max_width / w
    new_size = (max_width, int(image.shape[0] * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def extract_text(image: np.ndarray, max_width: int | None = MAX_OCR_WIDTH) -> str:
    """Jalankan OCR, gabungkan semua deteksi jadi satu string.

    max_width: batas lebar sebelum OCR (None = ukuran asli). Default 1000
    supaya perilaku existing tak berubah. Pemisahan per bahan ditangani di
    tahap tokenisasi terpisah, bukan di sini.
    """
    results = get_reader().readtext(_downscale(image, max_width), detail=0)
    return " ".join(results)
