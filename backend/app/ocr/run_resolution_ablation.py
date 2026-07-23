"""Ablation study: isolasi pengaruh tiap tahap preprocessing di max_width=2000.

Latar: resolusi penuh 12MP tidak memperbaiki kualitas OCR signifikan dan makan
71.4 detik/foto (terlalu lambat untuk user). Uji titik tengah (2000px) sambil
mengisolasi tahap preprocessing mana yang benar-benar berkontribusi.

Tiga kombinasi, semua max_width=2000, ke 6 foto resolusi tinggi yang sama:
  1. B_full_noThresh : grayscale + blur + CLAHE + deskew (skip threshold)
  2. gray_only       : grayscale saja (baseline paling minim)
  3. gray_blur       : grayscale + blur (titik tengah)

Output:
  dataset/debug_output/resolution_ablation_summary.txt

Jalankan dari folder backend/:
  python -m app.ocr.run_resolution_ablation
  python -m app.ocr.run_resolution_ablation --limit 1   # kanari 1 foto dulu
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import psutil

from app.ocr.reader import extract_text
from app.ocr.run_ocr_comparison import variant_b
from app.preprocessing.pipeline import reduce_noise, to_grayscale

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos"
SUMMARY_FILE = REPO_ROOT / "dataset" / "debug_output" / "resolution_ablation_summary.txt"

MAX_WIDTH = 2000
MIN_FREE_RAM_GB = 4.0  # di bawah ini, EasyOCR rawan OOM/thrashing di laptop 8GB

PHOTOS = [
    "curved/curved_001.jpeg",
    "curved/curved_003.jpeg",
    "curved/curved_005.jpeg",
    "normal/normal_003.jpeg",
    "glossy/glossy_015.jpeg",
    "small_text/small_text_022.jpeg",
]


def gray_only(image):
    """Kombinasi 2: grayscale saja."""
    return to_grayscale(image)


def gray_blur(image):
    """Kombinasi 3: grayscale + blur."""
    return reduce_noise(to_grayscale(image))


COMBOS = [
    ("B_full_noThresh", variant_b),  # gray+blur+CLAHE+deskew
    ("gray_only", gray_only),
    ("gray_blur", gray_blur),
]


def check_ram() -> bool:
    """Peringatkan kalau RAM bebas < MIN_FREE_RAM_GB. Return True kalau lanjut aman."""
    free_gb = psutil.virtual_memory().available / 1e9
    total_gb = psutil.virtual_memory().total / 1e9
    print(f"RAM bebas: {free_gb:.2f} GB dari {total_gb:.2f} GB")
    if free_gb < MIN_FREE_RAM_GB:
        print(
            f"\nPERINGATAN: RAM bebas < {MIN_FREE_RAM_GB} GB. EasyOCR di {MAX_WIDTH}px "
            f"rawan OOM/thrashing.\nTutup aplikasi berat dulu, atau lanjut dengan risiko."
        )
        return False
    return True


def main() -> None:
    if not check_ram() and "--force" not in sys.argv:
        print("Batal. Tambahkan --force kalau tetap mau jalan.")
        return

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    photos = PHOTOS[:limit] if limit else PHOTOS
    lines: list[str] = [f"Ablation preprocessing @ max_width={MAX_WIDTH}", ""]

    for rel in photos:
        image = cv2.imread(str(RAW_DIR / rel))
        if image is None:
            print(f"  [skip] gagal baca: {rel}")
            continue

        h, w = image.shape[:2]
        print(f"\n=== {rel}  ({w}x{h}) ===", flush=True)
        lines.append(f"=== {rel}  (asli {w}x{h}) ===")

        for label, combo_fn in COMBOS:
            start = time.perf_counter()
            text = extract_text(combo_fn(image), max_width=MAX_WIDTH)
            elapsed = time.perf_counter() - start

            print(f"  [{label:<16}] {elapsed:6.1f} detik, {len(text):4} karakter", flush=True)
            lines.append(f"[{label:<16} | {elapsed:.1f}s] {text}")

        lines.append("")

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSelesai. Ringkasan: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
