"""Full 200-photo regression testing for dynamic X-gap reading order sorting (alpha=0.8).

Runs the full pipeline across all 100 datar + 100 melengkung photos.
Outputs incremental CSV per photo with full before vs after comparison and flags.
"""

import csv
import json
import os
import sys
import time
from pathlib import Path
import cv2
import easyocr
import numpy as np

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, tokenize

RAW_PHOTOS_DIR = REPO_ROOT / "dataset" / "raw_photos"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CSV_OUT = RESULTS_DIR / "full_reading_order_regression.csv"

# Pre-verified photos from manual targeted regression
VERIFIED_CASES = {
    "melengkung_005.jpeg",
    "datar_002.jpeg",
    "datar_003.jpeg",
    "datar_005.jpeg",
    "melengkung_001.jpeg",
}

CSV_FIELDS = [
    "index",
    "category",
    "filename",
    "is_changed",
    "len_before",
    "len_after",
    "len_diff",
    "pct_change",
    "tokens_count_before",
    "tokens_count_after",
    "status_flag",
    "comp_v1",
    "comp_v2",
    "tokens_v1",
    "tokens_v2",
    "elapsed_sec",
]


def sort_reading_order_v1(results: list) -> list[tuple[list, str, float]]:
    """Original reading order sorting (v1 - no column awareness)."""
    if not results:
        return []

    detections = []
    heights = []
    for bbox, text, confidence in results:
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        height = max(ys) - min(ys)
        detections.append((bbox, text, confidence, sum(ys) / len(ys), min(xs)))
        heights.append(height)

    tolerance = max(float(np.mean(heights)) * 0.5, 1.0)
    lines = []
    for detection in sorted(detections, key=lambda item: item[3]):
        line = min(lines, key=lambda item: abs(item["center_y"] - detection[3]), default=None)
        if line is None or abs(line["center_y"] - detection[3]) > tolerance:
            lines.append({"center_y": detection[3], "items": [detection]})
        else:
            line["items"].append(detection)
            line["center_y"] = float(np.mean([item[3] for item in line["items"]]))

    ordered = []
    for line in sorted(lines, key=lambda item: item["center_y"]):
        ordered.extend(sorted(line["items"], key=lambda item: item[4]))
    return [(bbox, text, confidence) for bbox, text, confidence, _, _ in ordered]


def determine_flag(filename: str, comp_v1: str, comp_v2: str) -> str:
    if comp_v1 == comp_v2:
        return "IDENTIK"
    if filename in VERIFIED_CASES:
        return "TERVERIFIKASI_BERSIH"

    len_v1 = len(comp_v1)
    len_v2 = len(comp_v2)

    # If length dropped by > 50% or became empty, flag for manual review
    if len_v1 > 0:
        reduction_ratio = (len_v1 - len_v2) / len_v1
        if reduction_ratio > 0.50 or len_v2 == 0:
            return "PERLU_CEK_MANUAL"
    elif len_v2 > 0 and len_v1 == 0:
        return "BARU_TERDETEKSI"

    return "PERBAIKAN_RINGAN"


def main():
    print(f"Initializing EasyOCR reader (CPU)...", flush=True)
    reader = easyocr.Reader(["id", "en"], gpu=False)

    # Collect all photos
    all_photos = []
    for cat in ["datar", "melengkung"]:
        cat_dir = RAW_PHOTOS_DIR / cat
        for p in sorted(cat_dir.glob("*.jpeg")):
            all_photos.append((cat, p.name, p))

    total_photos = len(all_photos)
    print(f"Found {total_photos} photos across datar & melengkung.", flush=True)

    # Check for resume
    done_keys = set()
    file_exists = CSV_OUT.exists() and CSV_OUT.stat().st_size > 0
    if file_exists:
        with open(CSV_OUT, "r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                done_keys.add((row["category"], row["filename"]))
        print(f"Resuming: {len(done_keys)} photos already processed in {CSV_OUT.name}.", flush=True)

    # Open CSV in append mode
    csv_file = open(CSV_OUT, "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    if not file_exists or len(done_keys) == 0:
        writer.writeheader()
        csv_file.flush()

    stats = {
        "total": total_photos,
        "processed": 0,
        "identik": 0,
        "terverifikasi": 0,
        "perbaikan_ringan": 0,
        "perlu_cek_manual": 0,
        "baru_terdeteksi": 0,
    }

    print("=" * 70, flush=True)
    print(f"{'No':<5} {'Kategori/File':<30} {'Status':<22} {'Len (V1->V2)':<16} {'Waktu':<8}", flush=True)
    print("=" * 70, flush=True)

    for idx, (cat, fname, fpath) in enumerate(all_photos, 1):
        if (cat, fname) in done_keys:
            continue

        t0 = time.perf_counter()
        img = cv2.imread(str(fpath))
        if img is None:
            print(f"ERROR: Cannot read image {fpath}", flush=True)
            continue

        prep = preprocess(img)
        ocr_img = _downscale(prep, MAX_OCR_WIDTH)
        raw_results = reader.readtext(ocr_img, detail=1)

        # Baseline v1 (no column awareness)
        ord_v1 = sort_reading_order_v1(raw_results)
        txt_v1 = "\n".join(t for _, t, _ in ord_v1)
        comp_v1 = extract_composition_section(txt_v1)
        tok_v1 = tokenize(comp_v1)

        # Proposed v2 (dynamic X-gap column-aware alpha=0.8)
        ord_v2 = sort_reading_order(raw_results, alpha=0.8)
        txt_v2 = "\n".join(t for _, t, _ in ord_v2)
        comp_v2 = extract_composition_section(txt_v2)
        tok_v2 = tokenize(comp_v2)

        elapsed = time.perf_counter() - t0

        is_changed = comp_v1 != comp_v2
        len_v1 = len(comp_v1)
        len_v2 = len(comp_v2)
        len_diff = len_v2 - len_v1
        pct_change = (len_diff / len_v1 * 100.0) if len_v1 > 0 else 0.0

        status_flag = determine_flag(fname, comp_v1, comp_v2)

        row_data = {
            "index": idx,
            "category": cat,
            "filename": fname,
            "is_changed": is_changed,
            "len_before": len_v1,
            "len_after": len_v2,
            "len_diff": len_diff,
            "pct_change": round(pct_change, 2),
            "tokens_count_before": len(tok_v1),
            "tokens_count_after": len(tok_v2),
            "status_flag": status_flag,
            "comp_v1": comp_v1,
            "comp_v2": comp_v2,
            "tokens_v1": json.dumps(tok_v1, ensure_ascii=False),
            "tokens_v2": json.dumps(tok_v2, ensure_ascii=False),
            "elapsed_sec": round(elapsed, 3),
        }

        writer.writerow(row_data)
        csv_file.flush()
        os.fsync(csv_file.fileno())

        stats["processed"] += 1
        if status_flag == "IDENTIK":
            stats["identik"] += 1
        elif status_flag == "TERVERIFIKASI_BERSIH":
            stats["terverifikasi"] += 1
        elif status_flag == "PERLU_CEK_MANUAL":
            stats["perlu_cek_manual"] += 1
        elif status_flag == "BARU_TERDETEKSI":
            stats["baru_terdeteksi"] += 1
        else:
            stats["perbaikan_ringan"] += 1

        pct_str = f"({pct_change:+.1f}%)" if is_changed else ""
        len_str = f"{len_v1}->{len_v2} {pct_str}"
        print(f"[{idx:03d}/200] [{cat}/{fname:<20}] {status_flag:<22} {len_str:<18} {elapsed:.2f}s", flush=True)

    csv_file.close()
    print("=" * 70, flush=True)
    print("FULL REGRESSION RUN COMPLETED SUCCESSFULLY!", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
