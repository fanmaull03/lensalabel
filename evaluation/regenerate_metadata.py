"""Regenerate dataset/metadata.csv dari nol berdasarkan foto yang benar-benar
ada di dataset/raw_photos/<kategori>/.

Sumber : dataset/raw_photos/<kategori>/<nama>.jpeg
Output : dataset/metadata.csv   (filename,category)

Manifest lama DITIMPA total — tidak ada pencocokan dengan versi sebelumnya.
Kategori diambil dari nama subfolder, filename dari nama file (basename), agar
cocok dengan path yang dibaca run_ocr_evaluation.py: raw_photos/<category>/<filename>.

File yang bukan lowercase ".jpeg" (mis. ".JPG") tetap ikut dicatat tapi
diberi peringatan — konvensi dataset adalah .jpeg lowercase, jadi anomali
sebaiknya dirapikan manual, bukan disembunyikan skrip.

Jalankan dari root project:
  python evaluation/regenerate_metadata.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RAW_PHOTOS_DIR = Path(__file__).resolve().parent.parent / "dataset" / "raw_photos"
OUT_CSV = Path(__file__).resolve().parent.parent / "dataset" / "metadata.csv"
IMAGE_EXTS = {".jpeg", ".jpg"}  # dicek case-insensitive
CANONICAL_EXT = ".jpeg"  # konvensi dataset (lowercase)


def collect_rows() -> list[tuple[str, str]]:
    """Kumpulkan (filename, category) untuk tiap foto, urut per kategori lalu nama."""
    rows: list[tuple[str, str]] = []
    for category_dir in sorted(p for p in RAW_PHOTOS_DIR.iterdir() if p.is_dir()):
        category = category_dir.name
        for photo in sorted(category_dir.iterdir()):
            if not photo.is_file() or photo.suffix.lower() not in IMAGE_EXTS:
                continue
            if photo.suffix != CANONICAL_EXT:
                print(
                    f"  ! {category}/{photo.name}: bukan '{CANONICAL_EXT}' lowercase, "
                    "sebaiknya dirapikan",
                    file=sys.stderr,
                )
            rows.append((photo.name, category))
    return rows


def main() -> None:
    if not RAW_PHOTOS_DIR.is_dir():
        sys.exit(f"Folder tidak ditemukan: {RAW_PHOTOS_DIR}")

    rows = collect_rows()

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "category"])
        writer.writerows(rows)

    per_category: dict[str, int] = {}
    for _, category in rows:
        per_category[category] = per_category.get(category, 0) + 1

    print(f"metadata.csv ditulis ulang: {len(rows)} foto -> {OUT_CSV}")
    for category in sorted(per_category):
        print(f"  {category}: {per_category[category]}")


if __name__ == "__main__":
    main()
