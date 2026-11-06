"""Rebuild calibration GT after correcting R1 to operate on all spans per item."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from build_eval_gt_final import resolve_spans

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
DESTINATION = ROOT / "dataset/ground_truth/calibration_ingredients_gt_v2_2.json"
SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
SUMMARY = ROOT / "dataset/ground_truth/calibration_gt_v2_2_summary.json"


def main() -> None:
    if DESTINATION.exists() or SUMMARY.exists():
        raise FileExistsError("Output v2.2 sudah ada; skrip tidak menimpa file.")
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes.decode("utf-8-sig"))
    split = list(csv.DictReader(SPLIT.open(encoding="utf-8-sig", newline="")))
    allowed = {row["filename"] for row in split}
    texts = {row["filename"]: row["ground_truth_text"] for row in
             csv.DictReader(TRANSCRIPTS.open(encoding="utf-8-sig", newline=""))
             if row["filename"] in allowed}
    if set(texts) != allowed:
        raise ValueError("Transkrip kalibrasi tidak lengkap.")
    count_before = sum(len(row.get("ingredients", [])) for row in source.values())
    if count_before != 387:
        raise ValueError(f"GT kalibrasi sumber berubah: {count_before}; expected 387.")
    revised, resolutions, missing = resolve_spans(source, texts, allowed, "kalibrasi")
    pending = [row for row in resolutions if row["aturan"] == "R4" and row["tindakan"].startswith("MENUNGGU")]
    if pending:
        raise ValueError(f"GT kalibrasi memiliki R4 tertunda: {len(pending)}")
    DESTINATION.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    categories = Counter(item["category"] for doc in revised.values() for item in doc.get("ingredients", []))
    summary = {
        "source": str(SOURCE.relative_to(ROOT)), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "output": str(DESTINATION.relative_to(ROOT)), "output_sha256": hashlib.sha256(DESTINATION.read_bytes()).hexdigest(),
        "items_before": count_before,
        "items_after": sum(len(row.get("ingredients", [])) for row in revised.values()),
        "items_discarded_by_r1": len({row["_r1_dropped"] for row in resolutions if row.get("_r1_dropped")}),
        "r1_resolution_rows": sum(row["aturan"] == "R1" for row in resolutions),
        "resolution_counts": dict(Counter(row["aturan"] for row in resolutions)),
        "missing_spans": missing, "categories": dict(categories),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
