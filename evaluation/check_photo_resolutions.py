"""
Cek resolusi native seluruh foto di dataset/raw_photos/, untuk memastikan
apakah resolusi rendah (960x1280) yang ketemu di 5 sample kemarin cuma
kebetulan pada sample itu, atau memang berlaku ke seluruh dataset.

Jalankan dari root folder project (bukan dari dalam backend/):
  python evaluation/check_photo_resolutions.py
"""

from collections import defaultdict
from pathlib import Path

from PIL import Image

RAW_PHOTOS_DIR = Path(__file__).resolve().parent.parent / "dataset" / "raw_photos"

# Ambang batas "resolusi rendah". 2000px di sisi terpanjang masih longgar,
# kamera HP modern normalnya jauh di atas ini (3000-4000px+).
LOW_RES_THRESHOLD = 2000


def main() -> None:
    if not RAW_PHOTOS_DIR.exists():
        print(f"Folder tidak ditemukan: {RAW_PHOTOS_DIR}")
        return

    resolution_counts: dict[tuple[int, int], int] = defaultdict(int)
    low_res_files: list[tuple[str, int, int]] = []
    total = 0

    for category_dir in sorted(RAW_PHOTOS_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        for image_path in sorted(category_dir.glob("*.jp*g")):
            with Image.open(image_path) as img:
                w, h = img.size
            resolution_counts[(w, h)] += 1
            total += 1
            if max(w, h) < LOW_RES_THRESHOLD:
                low_res_files.append((str(image_path.relative_to(RAW_PHOTOS_DIR)), w, h))

    print(f"Total foto ditemukan: {total}\n")

    print("=== Distribusi resolusi (width x height) ===")
    for (w, h), count in sorted(resolution_counts.items(), key=lambda x: -x[1]):
        print(f"{w}x{h}: {count} foto")

    print(f"\n=== Foto dengan sisi terpanjang < {LOW_RES_THRESHOLD}px ({len(low_res_files)} dari {total}) ===")
    for filename, w, h in low_res_files:
        print(f"{filename}: {w}x{h}")

    if total and low_res_files:
        pct = len(low_res_files) / total * 100
        print(f"\n{pct:.1f}% dari dataset kamu resolusinya di bawah {LOW_RES_THRESHOLD}px.")


if __name__ == "__main__":
    main()
