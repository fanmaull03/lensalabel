"""Uji performa OCR pada foto resolusi tinggi (12.2 MP) TANPA downscale.

Preprocessing varian B (skip threshold), max_width=None (resolusi penuh),
sesuai temuan eksperimen sebelumnya.

PERINGATAN: resolusi penuh 3024x4032 = ~16x piksel dibanding baseline 1000px.
Memory EasyOCR naik kira-kira linear terhadap luas piksel, jadi di laptop 8GB
ini rawan OOM/swap. Pakai --limit N untuk uji sebagian dulu.

Output:
  dataset/debug_output/highres_test_summary.txt   (ringkasan semua foto)
  dataset/debug_output/highres_test/<nama>.txt    (satu file per foto)

Jalankan dari folder backend/:
  python -m app.ocr.run_highres_test            # semua 6 foto
  python -m app.ocr.run_highres_test --limit 1  # kanari, 1 foto dulu
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

from app.ocr.reader import extract_text
from app.ocr.run_ocr_comparison import variant_b

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos"
DEBUG_DIR = REPO_ROOT / "dataset" / "debug_output"
SUMMARY_FILE = DEBUG_DIR / "highres_test_summary.txt"
PER_PHOTO_DIR = DEBUG_DIR / "highres_test"

# 6 foto hasil transfer ulang resolusi tinggi (semua 3024x4032 menurut cv2)
PHOTOS = [
    "curved/curved_001.jpeg",
    "curved/curved_003.jpeg",
    "curved/curved_005.jpeg",
    "normal/normal_003.jpeg",
    "glossy/glossy_015.jpeg",
    "small_text/small_text_022.jpeg",
]


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    PER_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photos = PHOTOS[:limit] if limit else PHOTOS
    lines: list[str] = []

    for rel in photos:
        image = cv2.imread(str(RAW_DIR / rel))
        if image is None:
            print(f"  [skip] gagal baca: {rel}")
            continue

        h, w = image.shape[:2]
        print(f"OCR {rel}  ({w}x{h}, {w * h / 1e6:.1f} MP, tanpa downscale) ...", flush=True)

        start = time.perf_counter()
        text = extract_text(variant_b(image), max_width=None)  # None = resolusi penuh
        elapsed = time.perf_counter() - start
        print(f"  selesai dalam {elapsed:.1f} detik, {len(text)} karakter", flush=True)

        stem = Path(rel).stem
        (PER_PHOTO_DIR / f"{stem}.txt").write_text(text, encoding="utf-8")
        lines += [f"=== {rel}  ({w}x{h}, {elapsed:.1f} detik) ===", text, ""]

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSelesai. Ringkasan: {SUMMARY_FILE}\nPer foto: {PER_PHOTO_DIR}")


if __name__ == "__main__":
    main()
