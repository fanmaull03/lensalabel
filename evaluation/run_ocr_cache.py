"""Preprocess and OCR each split photo once, saving resumable raw detections."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.ocr.reader import MAX_OCR_WIDTH, _downscale, get_reader  # noqa: E402
from app.preprocessing.pipeline import preprocess  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-csv", required=True, type=Path)
    parser.add_argument("--photos-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    args = parser.parse_args()
    with args.split_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"No photos listed in {args.split_csv}")
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    reader = None
    total = len(rows)
    for index, row in enumerate(rows, 1):
        filename, category = row["filename"], row["category"]
        cache_path = args.cache_dir / f"{filename}.json"
        if cache_path.exists():
            print(f"[{index}/{total}] {filename}: cache exists, skip")
            continue
        started = time.perf_counter()
        image_path = args.photos_dir / category / filename
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"[{index}/{total}] {filename}: missing/unreadable ({image_path}), skip")
            continue
        if reader is None:
            reader = get_reader()
        detections = reader.readtext(_downscale(preprocess(image), MAX_OCR_WIDTH), detail=1)
        payload = {
            "filename": filename,
            "category": category,
            "detections": [
                {"bbox": [[float(x), float(y)] for x, y in bbox], "text": text, "confidence": float(confidence)}
                for bbox, text, confidence in detections
            ],
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elapsed = time.perf_counter() - started
        print(f"[{index}/{total}] {filename}: {len(detections)} detections, {elapsed:.2f}s")


if __name__ == "__main__":
    main()
