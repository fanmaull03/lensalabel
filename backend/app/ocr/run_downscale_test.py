"""Uji hipotesis: seberapa besar pengaruh downscale ke kualitas OCR.

Jalankan OCR ke 5 foto terburuk dengan tiga nilai max_width: None (ukuran
asli), 1600, dan 1000 (baseline). Preprocessing pakai varian B (skip
threshold), yang lebih unggul dari eksperimen sebelumnya.

Output ringkasan: dataset/debug_output/downscale_test_summary.txt

Jalankan dari folder backend/:
  python -m app.ocr.run_downscale_test
"""

from __future__ import annotations

from pathlib import Path

import cv2

from app.ocr.reader import extract_text
from app.ocr.run_ocr_comparison import variant_b

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos"
OUT_FILE = REPO_ROOT / "dataset" / "debug_output" / "downscale_test_summary.txt"

PHOTOS = [
    "glossy/glossy_002.jpeg",
    "glossy/glossy_004.jpeg",
    "curved/curved_005.jpeg",
    "curved/curved_008.jpeg",
    "glossy/glossy_008.jpeg",
]
MAX_WIDTHS = [None, 1600, 1000]  # None = ukuran asli


def main() -> None:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    for rel in PHOTOS:
        image = cv2.imread(str(RAW_DIR / rel))
        if image is None:
            print(f"  [skip] gagal baca: {rel}")
            continue

        h, w = image.shape[:2]
        print(f"OCR {rel}  (asli {w}x{h}) ...")
        processed = variant_b(image)  # varian B dijalankan sekali, dipakai ketiga max_width

        lines += [f"=== {rel}  (ukuran asli {w}x{h}) ==="]
        for mw in MAX_WIDTHS:
            label = "asli" if mw is None else str(mw)
            text = extract_text(processed, max_width=mw)
            lines.append(f"[max_width={label:<5}] {text}")
        lines.append("")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSelesai. Ringkasan di {OUT_FILE}")


if __name__ == "__main__":
    main()
