"""Paketkan kode, GT final, KB snapshot, dan hanya 40 foto kalibrasi untuk Colab."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "evaluation/results/lensalabel_calibration_v4_bundle.zip"
CODE_FILES = [
    "backend/app/__init__.py", "backend/app/db/__init__.py", "backend/app/db/models.py",
    "backend/app/matching/__init__.py", "backend/app/matching/fuzzy_matcher.py",
    "backend/app/classifier/__init__.py", "backend/app/classifier/rule_based.py",
    "backend/app/ocr/__init__.py", "backend/app/ocr/reader.py",
    "backend/app/preprocessing/__init__.py", "backend/app/preprocessing/pipeline.py",
    "backend/app/tokenizer/__init__.py", "backend/app/tokenizer/tokenizer.py",
    "evaluation/run_ocr_cache.py", "evaluation/run_grid_search.py",
    "evaluation/kb_snapshot.json", "evaluation/splits/calibration_set.csv",
    "evaluation/requirements-colab.txt",
    "dataset/ground_truth/calibration_ingredients_gt_final.json",
    "dataset/ground_truth/calibration_review_v4.xlsx",
]


def main() -> None:
    with (ROOT / "evaluation/splits/calibration_set.csv").open(encoding="utf-8-sig", newline="") as source:
        split = list(csv.DictReader(source))
    if len(split) != 40 or len({row["filename"] for row in split}) != 40 or Counter(row["category"] for row in split) != {"datar": 20, "melengkung": 20}:
        raise ValueError("Bundle harus berisi split kalibrasi 40 foto yang unik, 20 per kategori.")
    final_gt = json.loads((ROOT / CODE_FILES[-2]).read_text(encoding="utf-8"))
    if set(final_gt) != {row["filename"] for row in split}:
        raise ValueError("GT final tidak sesuai dengan split kalibrasi.")
    photo_root = (ROOT / "dataset/raw_photos").resolve()
    photos = []
    for row in split:
        path = (photo_root / row["category"] / row["filename"]).resolve()
        if not path.is_relative_to(photo_root) or not path.is_file():
            raise ValueError(f"Foto kalibrasi tidak tersedia: {row['filename']}")
        photos.append(path.relative_to(ROOT).as_posix())
    names = CODE_FILES + photos
    manifest = {
        "split": "calibration", "n_photos": 40,
        "gt_ingredients": sum(len(info["ingredients"]) for info in final_gt.values()),
        "files_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names},
    }
    if OUTPUT.exists():
        raise FileExistsError("Bundle sudah ada; arsipkan dahulu sebelum membuat ulang.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=4) as archive:
        for name in names:
            archive.write(ROOT / name, arcname=name)
        archive.writestr("bundle_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(OUTPUT) as archive:
        if archive.testzip() is not None:
            raise ValueError("Verifikasi ZIP gagal.")
    print(f"Bundle: {OUTPUT}\n40 foto; {manifest['gt_ingredients']} anotasi final; {OUTPUT.stat().st_size / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
