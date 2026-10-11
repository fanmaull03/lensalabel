"""Tahap 2 - Image preprocessing (OpenCV).

Empat tahap berurutan sesuai proposal skripsi:
    1. grayscale -> 2. Gaussian blur -> 3. CLAHE -> 4. deskew

Tiap tahap dibuat sebagai fungsi terpisah supaya bisa dites satu per satu.
Semua fungsi menerima dan mengembalikan numpy.ndarray (citra OpenCV, BGR/gray).

Parameter di bawah adalah "knob" kalibrasi. Nilainya masuk akal untuk foto
kemasan makanan (glossy, melengkung, teks kecil, cahaya tidak merata), tapi
tetap perlu dituning ulang kalau karakteristik dataset berubah.
"""

from __future__ import annotations

import cv2
import numpy as np

# --- Knob kalibrasi (silakan tuning kalau hasil kurang bagus) ---------------

# Kernel ganjil kecil (3x3). Cukup meredam derau sensor kamera HP pada teks
# kecil tanpa "menelan" garis huruf yang tipis. Kernel besar (mis. 7x7) bikin
# teks kecil kabur dan malah menurunkan akurasi OCR.
GAUSSIAN_KERNEL = (3, 3)

# clipLimit rendah (2.0) menaikkan kontras lokal tanpa meledakkan noise di area
# glossy/pantulan cahaya. tileGridSize 8x8 = kontras dihitung per-blok, jadi
# pencahayaan tidak merata (bayangan tangan, pantulan lampu) diratakan lokal.
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)

def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Tahap 1: buang informasi warna, sisakan 1 kanal intensitas."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def reduce_noise(gray: np.ndarray) -> np.ndarray:
    """Tahap 2: Gaussian blur untuk meredam derau titik piksel acak."""
    return cv2.GaussianBlur(gray, GAUSSIAN_KERNEL, 0)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """Tahap 3: CLAHE, ratakan kontras secara lokal (adaptif per-tile)."""
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)
    return clahe.apply(gray)


def deskew(gray: np.ndarray) -> np.ndarray:
    """Tahap 4: luruskan kemiringan teks akibat sudut foto.

    Sudut dihitung dari kontur foreground terbesar saja, bukan seluruh
    piksel gelap, supaya estimasi lebih tahan terhadap noise latar
    belakang yang ikut jadi hitam setelah threshold.
    """
    contours, _ = cv2.findContours(255 - gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return gray

    largest = max(contours, key=cv2.contourArea)
    angle = cv2.minAreaRect(largest)[-1]
    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90

    # Lewati rotasi jika sudut kemiringan mendekati 0 (<0.5 derajat)
    if abs(angle) < 0.5:
        return gray

    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# Urutan tahap: dipakai runner test dan integrasi FastAPI.
STAGES = [
    ("grayscale", to_grayscale),
    ("blur", reduce_noise),
    ("clahe", enhance_contrast),
    ("deskew", deskew),
]


def preprocess(image: np.ndarray) -> np.ndarray:
    """Jalankan keempat tahap berurutan, kembalikan citra siap-OCR."""
    for _, stage_fn in STAGES:
        image = stage_fn(image)
    return image
