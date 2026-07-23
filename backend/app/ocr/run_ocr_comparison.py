"""Bandingkan kualitas OCR dua varian pipeline pada sample kecil.

Varian A: preprocessing lengkap (grayscale, blur, CLAHE, adaptive threshold, deskew)
Varian B: sama tapi SKIP adaptive threshold (grayscale, blur, CLAHE, deskew)

Belum pakai ground truth resmi; hasil teks disimpan mentah untuk dibaca manual.
Output ke dataset/debug_output/ocr_comparison/:
  <foto>_A.txt, <foto>_B.txt, dan _summary.txt (kedua varian bersebelahan).

Jalankan dari folder backend/:
  python -m app.ocr.run_ocr_comparison
"""

from __future__ import annotations

from pathlib import Path

import cv2

from app.ocr.reader import extract_text
from app.preprocessing.pipeline import (
    enhance_contrast,
    deskew,
    preprocess,
    reduce_noise,
    to_grayscale,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos"
OUT_DIR = REPO_ROOT / "dataset" / "debug_output" / "ocr_comparison"

CONDITIONS = ["glossy", "curved"]
SAMPLES_PER_CONDITION = 8  # sample kecil dulu, cukup untuk baca manual


def variant_a(image):
    """Pipeline lengkap (5 tahap)."""
    return preprocess(image)


def variant_b(image):
    """Tanpa adaptive threshold: grayscale -> blur -> CLAHE -> deskew."""
    return deskew(enhance_contrast(reduce_noise(to_grayscale(image))))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_lines: list[str] = []

    for condition in CONDITIONS:
        photos = sorted((RAW_DIR / condition).glob("*.jpeg"))[:SAMPLES_PER_CONDITION]
        for photo in photos:
            image = cv2.imread(str(photo))
            if image is None:
                print(f"  [skip] gagal baca: {photo.name}")
                continue

            print(f"OCR {condition}/{photo.name} ...")
            text_a = extract_text(variant_a(image))
            text_b = extract_text(variant_b(image))

            (OUT_DIR / f"{photo.stem}_A.txt").write_text(text_a, encoding="utf-8")
            (OUT_DIR / f"{photo.stem}_B.txt").write_text(text_b, encoding="utf-8")

            summary_lines += [
                f"=== {condition}/{photo.name} ===",
                f"[A full     ] {text_a}",
                f"[B no-thresh] {text_b}",
                "",
            ]

    (OUT_DIR / "_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\nSelesai. Hasil di {OUT_DIR} (lihat _summary.txt untuk perbandingan).")


if __name__ == "__main__":
    main()
