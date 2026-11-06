"""Create calibration GT v2.1 by applying only audited R1 span resolutions."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from build_eval_gt_final import resolve_spans

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
DESTINATION = ROOT / "dataset/ground_truth/calibration_ingredients_gt_v2_1.json"
ARCHIVE = ROOT / "archive/ground_truth/calibration_ingredients_gt_v2_pre_v2_1.json"
SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
SUMMARY = ROOT / "dataset/ground_truth/calibration_gt_v2_1_summary.json"


def main() -> None:
    if DESTINATION.exists() or ARCHIVE.exists() or SUMMARY.exists():
        raise FileExistsError("Output/archive v2.1 sudah ada; skrip tidak menimpa file.")
    source_bytes = SOURCE.read_bytes()
    original = json.loads(source_bytes.decode("utf-8-sig"))
    split_rows = list(csv.DictReader(SPLIT.open(encoding="utf-8-sig", newline="")))
    allowed = {row["filename"] for row in split_rows}
    texts = {row["filename"]: row["ground_truth_text"] for row in
             csv.DictReader(TRANSCRIPTS.open(encoding="utf-8-sig", newline=""))
             if row["filename"] in allowed}
    if set(texts) != allowed:
        raise ValueError("Transkrip kalibrasi tidak lengkap.")
    count_before = sum(len(row.get("ingredients", [])) for row in original.values())
    if count_before != 387:
        raise ValueError(f"GT kalibrasi sumber berubah: {count_before} item, expected 387.")
    revised, resolutions, missing = resolve_spans(original, texts, allowed, "kalibrasi")
    unresolved = [row for row in resolutions if row["aturan"] == "R4"]
    if unresolved:
        raise ValueError(f"GT kalibrasi memiliki R4 yang belum terselesaikan: {len(unresolved)}")
    if any(row["aturan"] not in {"R1", "R3"} for row in resolutions):
        raise ValueError("Ada resolusi selain R1/R3; tidak dibuat v2.1.")
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, ARCHIVE)
    DESTINATION.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    categories = Counter(item["category"] for doc in revised.values() for item in doc.get("ingredients", []))
    before_hash = hashlib.sha256(source_bytes).hexdigest()
    summary = {
        "source": str(SOURCE.relative_to(ROOT)), "source_sha256": before_hash,
        "archive": str(ARCHIVE.relative_to(ROOT)), "output": str(DESTINATION.relative_to(ROOT)),
        "items_before": count_before,
        "items_after": sum(len(row.get("ingredients", [])) for row in revised.values()),
        "items_discarded_by_r1": len({row["_r1_dropped"] for row in resolutions if row.get("_r1_dropped")}),
        "resolution_counts": dict(Counter(row["aturan"] for row in resolutions)),
        "r1_rows": [row for row in resolutions if row["aturan"] == "R1"],
        "r3_rows": [row for row in resolutions if row["aturan"] == "R3"],
        "missing_spans": missing, "categories": dict(categories),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"r1_rows", "r3_rows", "missing_spans"}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
