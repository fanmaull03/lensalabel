"""Evaluate cached OCR detections over fuzzy-match thresholds (no OCR calls)."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.classifier.rule_based import classify_product  # noqa: E402
from app.matching.fuzzy_matcher import load_knowledge_base_from_json, match_token, match_token_many  # noqa: E402
from app.ocr.reader import sort_reading_order  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402


def runtime_versions() -> dict[str, str]:
    def package(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "not-installed"
    import cv2
    return {"easyocr": package("easyocr"), "torch": package("torch"), "cv2.__version__": cv2.__version__,
            "cv2.__file__": str(cv2.__file__)}

THRESHOLDS = (70, 75, 80, 85, 90, 95)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-csv", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--kb-json", required=True, type=Path)
    parser.add_argument("--ground-truth-json", required=True, type=Path)
    parser.add_argument("--detail-csv", required=True, type=Path)
    parser.add_argument("--summary-csv", required=True, type=Path)
    parser.add_argument("--matcher", choices=("old", "many", "many_shared"), default="many_shared")
    args = parser.parse_args()
    versions = runtime_versions()
    print("Runtime paket: " + json.dumps(versions, ensure_ascii=False), flush=True)

    with args.split_csv.open(newline="", encoding="utf-8-sig") as f:
        split_rows = list(csv.DictReader(f))
    ground_truth = json.loads(args.ground_truth_json.read_text(encoding="utf-8-sig"))
    kb = load_knowledge_base_from_json(args.kb_json)
    details: list[dict] = []
    totals = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for photo_index, row in enumerate(split_rows, 1):
        filename = row["filename"]
        cache_path = args.cache_dir / f"{filename}.json"
        if not cache_path.exists():
            raise FileNotFoundError(f"OCR cache not found: {cache_path}")
        cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        ordered = sort_reading_order([
            (d["bbox"], d["text"], float(d["confidence"]))
            for d in cache["detections"]
        ])
        raw_text = "\n".join(text for _, text, _ in ordered)
        tokens = tokenize(extract_composition_section(raw_text))
        gt_entry = ground_truth.get(filename)
        if gt_entry is None:
            raise KeyError(f"Ground truth has no entry for {filename}")
        gt_names = {item["standard_name"] for item in gt_entry.get("ingredients", [])}

        for threshold in THRESHOLDS:
            matches = (
                [match_token(token, kb, threshold=float(threshold)) for token in tokens]
                if args.matcher == "old" else
                [match for token in tokens for match in match_token_many(
                    token, kb, threshold=float(threshold), shared_heads=args.matcher == "many_shared",
                )]
            )
            classified = classify_product(matches)
            predicted = {
                item["standard_name"]
                for category in ("aman", "perhatian", "hindari")
                for item in classified[category]
            }
            tp_set = predicted & gt_names
            fp_set = predicted - gt_names
            fn_set = gt_names - predicted
            tp, fp, fn = len(tp_set), len(fp_set), len(fn_set)
            totals[threshold]["tp"] += tp
            totals[threshold]["fp"] += fp
            totals[threshold]["fn"] += fn
            details.append({
                "filename": filename,
                "category": row["category"],
                "threshold": threshold,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
                "ground_truth": json.dumps(sorted(gt_names), ensure_ascii=False),
                "predicted": json.dumps(sorted(predicted), ensure_ascii=False),
                "true_positive": json.dumps(sorted(tp_set), ensure_ascii=False),
                "false_positive": json.dumps(sorted(fp_set), ensure_ascii=False),
                "false_negative": json.dumps(sorted(fn_set), ensure_ascii=False),
                "verdict": classified["verdict"],
            })
        print(f"[{photo_index}/{len(split_rows)}] {filename}: evaluated thresholds {THRESHOLDS}")

    summaries = []
    for threshold in THRESHOLDS:
        tp, fp, fn = (totals[threshold][key] for key in ("tp", "fp", "fn"))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        summaries.append({
            "threshold": threshold,
            "n_photos": len(split_rows),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        })
    write_csv(args.detail_csv, details, list(details[0]) if details else ["filename", "category", "threshold", "tp", "fp", "fn"])
    write_csv(args.summary_csv, summaries, ["threshold", "n_photos", "tp", "fp", "fn", "precision", "recall", "f1"])
    print(f"Details: {args.detail_csv}\nSummary: {args.summary_csv}")


if __name__ == "__main__":
    main()
