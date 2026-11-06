"""Gabungkan file ground truth per-kategori jadi satu transcripts.csv.

Sumber : dataset/ground_truth/<kategori>/<nama>.txt  (satu file per foto)
Output : dataset/ground_truth/transcripts.csv        (filename,category,ground_truth_text)

filename memakai ekstensi foto (.jpeg) supaya cocok dengan path yang dibaca
run_ocr_evaluation.py: raw_photos/<category>/<filename>.

Jalankan ulang tiap kali ada .txt baru:
  python evaluation/build_transcripts_csv.py
"""

from __future__ import annotations

import csv
from pathlib import Path

GT_DIR = Path(__file__).resolve().parent.parent / "dataset" / "ground_truth"
OUT_CSV = GT_DIR / "transcripts.csv"
PHOTO_EXT = ".jpeg"


def main() -> None:
    rows = []
    for txt in sorted(GT_DIR.rglob("*.txt")):
        category = txt.parent.name
        text = txt.read_text(encoding="utf-8").strip()
        rows.append(
            {
                "filename": txt.stem + PHOTO_EXT,
                "category": category,
                "ground_truth_text": text,
            }
        )

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "category", "ground_truth_text"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Selesai. {len(rows)} baris ditulis ke {OUT_CSV}")


if __name__ == "__main__":
    main()
