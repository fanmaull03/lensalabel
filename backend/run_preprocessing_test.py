"""Runner uji preprocessing (standalone, di luar FastAPI).

Baca semua foto di dataset/raw_photos/<kondisi>/, jalankan pipeline lengkap,
dan simpan hasil SETIAP tahap ke dataset/debug_output/ supaya bisa dibandingkan
before/after per tahap.

Nama file output: <nama_foto>_<no>_<tahap>.jpg
  contoh: curved_001_1_original.jpg, curved_001_2_grayscale.jpg, ...

Jalankan dari folder backend/:
  python run_preprocessing_test.py
"""

from __future__ import annotations

from pathlib import Path

import cv2

from app.preprocessing.pipeline import STAGES

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos"
OUT_DIR = REPO_ROOT / "dataset" / "debug_output"


def process_one(image_path: Path) -> int:
    """Proses satu foto, simpan original + hasil tiap tahap. Return jumlah file ditulis."""
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"  [skip] gagal baca: {image_path.name}")
        return 0

    stem = image_path.stem
    written = 0

    # No. 1 = citra asli sebagai pembanding
    cv2.imwrite(str(OUT_DIR / f"{stem}_1_original.jpg"), image)
    written += 1

    # Tahap 2 dst = hasil tiap fungsi pipeline, dijalankan berurutan
    current = image
    for idx, (name, stage_fn) in enumerate(STAGES, start=2):
        current = stage_fn(current)
        cv2.imwrite(str(OUT_DIR / f"{stem}_{idx}_{name}.jpg"), current)
        written += 1

    return written


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    photos = sorted(RAW_DIR.rglob("*.jpeg"))
    if not photos:
        print(f"Tidak ada foto .jpeg di {RAW_DIR}")
        return

    total_files = 0
    for photo in photos:
        print(f"Proses {photo.relative_to(RAW_DIR)} ...")
        total_files += process_one(photo)

    print(f"\nSelesai. {len(photos)} foto -> {total_files} file di {OUT_DIR}")


if __name__ == "__main__":
    main()
