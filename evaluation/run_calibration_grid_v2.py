"""Prepared grid search for the 40 calibration photos using cached OCR only.

Run only after the threshold experiment is authorized. This script refuses a
split other than the exact 40-photo calibration manifest and never opens the
160-photo evaluation manifest or images.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
from functools import lru_cache
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.matching import fuzzy_matcher as matcher_module  # noqa: E402
# The matcher results are unchanged; larger memoization tables avoid recomputing
# the same candidate windows for seven thresholds in this offline experiment.
matcher_module._many_score = lru_cache(maxsize=500_000)(matcher_module._many_score.__wrapped__)
matcher_module._best_fragment = lru_cache(maxsize=100_000)(matcher_module._best_fragment.__wrapped__)
from app.matching.fuzzy_matcher import match_token_many  # noqa: E402
from app.ocr.reader import sort_reading_order  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402

SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
GT = ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
KB = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
OCR_CACHE = ROOT / "evaluation/results/colab_v4/ocr_cache"
OUT = ROOT / "evaluation/results/provisional_cached_ocr"
THRESHOLDS = tuple(range(65, 100, 5))
CATEGORIES = ("aman", "perhatian", "hindari")
BOOTSTRAP_ITERATIONS = 1000
BOOTSTRAP_SEED = 42


def flatten_kb(doc: dict) -> list[dict]:
    entries = doc["ingredients"]
    used: set[int] = set()
    next_id = max((int(x) for e in entries for x in e.get("old_entry_ids", [])), default=0) + 1
    flattened = []
    for entry in entries:
        iid = next((int(x) for x in entry.get("old_entry_ids", []) if int(x) not in used), None)
        if iid is None:
            while next_id in used:
                next_id += 1
            iid = next_id
            next_id += 1
        used.add(iid)
        for variant in [entry["standard_name"], *entry.get("synonyms", [])]:
            if variant:
                flattened.append({"ingredient_id": iid, "standard_name": entry["standard_name"],
                                  "category": entry["category"], "name_variant": variant})
    return flattened


def metrics(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percent
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_intervals(per_photo: dict, category_by_name: dict[str, str]) -> list[dict]:
    """Percentile 95% CIs from photo-level resampling, shared draws per threshold."""
    filenames = list(per_photo)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = [[rng.randrange(len(filenames)) for _ in filenames]
             for _ in range(BOOTSTRAP_ITERATIONS)]
    results = []
    for threshold in THRESHOLDS:
        f1_values, avoid_recall_values = [], []
        for indices in draws:
            tp = fp = fn = avoid_tp = avoid_fn = 0
            for index in indices:
                photo = per_photo[filenames[index]]
                expected = photo["gt"]
                predicted = photo["predictions"][threshold]
                tp += len(expected & predicted)
                fp += len(predicted - expected)
                fn += len(expected - predicted)
                expected_avoid = {name for name in expected if category_by_name.get(name) == "hindari"}
                predicted_avoid = {name for name in predicted if category_by_name.get(name) == "hindari"}
                avoid_tp += len(expected_avoid & predicted_avoid)
                avoid_fn += len(expected_avoid - predicted_avoid)
            _precision, _recall, f1 = metrics(tp, fp, fn)
            f1_values.append(f1)
            avoid_recall_values.append(avoid_tp / (avoid_tp + avoid_fn) if avoid_tp + avoid_fn else 0.0)
        results.append({
            "threshold": threshold,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "seed": BOOTSTRAP_SEED,
            "f1_ci95_low": percentile(f1_values, 0.025),
            "f1_ci95_high": percentile(f1_values, 0.975),
            "hindari_recall_ci95_low": percentile(avoid_recall_values, 0.025),
            "hindari_recall_ci95_high": percentile(avoid_recall_values, 0.975),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr-ablation-detail", type=Path,
                        help="Optional OCR detail CSV from Colab ablation; reuse selected OCR text without OCR rerun.")
    parser.add_argument("--gt-json", type=Path, default=GT,
                        help="Calibration GT JSON; defaults to the current calibration GT.")
    parser.add_argument("--output-suffix", default="",
                        help="Optional output-directory suffix for versioned GT runs.")
    parser.add_argument("--max-ocr-width", type=int, choices=(1000, 1500, 2000), default=2000)
    parser.add_argument("--adaptive-threshold", choices=("on", "off"), default="off")
    args = parser.parse_args()
    with SPLIT.open(encoding="utf-8-sig", newline="") as f:
        split = list(csv.DictReader(f))
    if len(split) != 40 or len({r["filename"] for r in split}) != 40:
        raise RuntimeError("Grid dibatasi pada tepat 40 foto kalibrasi unik.")
    gt_path = args.gt_json if args.gt_json.is_absolute() else ROOT / args.gt_json
    gt = json.loads(gt_path.read_text(encoding="utf-8-sig"))
    if set(gt) != {row["filename"] for row in split}:
        raise RuntimeError("GT harus berisi tepat seluruh 40 foto kalibrasi.")
    kb_doc = json.loads(KB.read_text(encoding="utf-8-sig"))
    kb = flatten_kb(kb_doc)
    category_by_name = {entry["standard_name"]: entry["category"] for entry in kb_doc["ingredients"]}
    selected_ocr_text = None
    if args.ocr_ablation_detail:
        config_key = f"width_{args.max_ocr_width}_adaptive_{args.adaptive_threshold}"
        suffix = f"_{args.output_suffix}" if args.output_suffix else ""
        output_dir = ROOT / f"evaluation/results/grid_{config_key}{suffix}"
        with args.ocr_ablation_detail.open(encoding="utf-8-sig", newline="") as stream:
            selected_ocr_text = {row["filename"]: row["ocr_text"] for row in csv.DictReader(stream)
                                 if row.get("config_key") == config_key}
        if set(selected_ocr_text) != {row["filename"] for row in split}:
            raise RuntimeError(f"Ablation detail harus berisi konfigurasi {config_key} untuk tepat 40 foto kalibrasi.")
    else:
        output_dir = OUT
    per_photo = {}
    for row in split:
        filename, condition = row["filename"], row["category"]
        if filename not in gt:
            raise KeyError(f"GT tidak memuat foto kalibrasi {filename}")
        if selected_ocr_text is not None:
            raw = selected_ocr_text[filename]
        else:
            cache_path = OCR_CACHE / f"{filename}.json"
            if not cache_path.exists():
                raise FileNotFoundError(f"Cache OCR belum ada: {cache_path}; buat cache hanya untuk 40 foto ini.")
            cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
            ordered = sort_reading_order([(d["bbox"], d["text"], float(d["confidence"])) for d in cache["detections"]])
            raw = "\n".join(text for _, text, _ in ordered)
        tokens = tokenize(extract_composition_section(raw))
        expected = {item["standard_name"] for item in gt[filename].get("ingredients", [])}
        predictions_by_threshold = {}
        for threshold in THRESHOLDS:
            matched = [m for token in tokens for m in match_token_many(token, kb, threshold=float(threshold), shared_heads=True) if m.matched]
            predictions_by_threshold[threshold] = {m.standard_name for m in matched}
        per_photo[filename] = {"condition": condition, "gt": expected, "predictions": predictions_by_threshold}
        print(f"[{len(per_photo)}/40] selesai {filename}", flush=True)

    summary_rows = []
    detail_rows = []
    scopes = [("Keseluruhan", lambda _row: True), ("Datar", lambda row: row["condition"] == "datar"),
              ("Melengkung", lambda row: row["condition"] == "melengkung")]
    for threshold in THRESHOLDS:
        for scope_name, include in scopes:
            chosen = [row for row in per_photo.values() if include(row)]
            for category in ("semua", *CATEGORIES):
                tp = fp = fn = 0
                for photo in chosen:
                    expected = photo["gt"]
                    predicted = photo["predictions"][threshold]
                    in_category = (lambda name: True) if category == "semua" else (lambda name, c=category: category_by_name.get(name) == c)
                    tp += sum(1 for name in expected & predicted if in_category(name))
                    fp += sum(1 for name in predicted - expected if in_category(name))
                    fn += sum(1 for name in expected - predicted if in_category(name))
                p, r, f1 = metrics(tp, fp, fn)
                summary_rows.append({"threshold": threshold, "cakupan": scope_name, "kategori": category,
                                     "foto": len(chosen), "tp": tp, "fp": fp, "fn": fn,
                                     "precision": p, "recall": r, "f1": f1})
        for filename, photo in per_photo.items():
            expected, predicted = photo["gt"], photo["predictions"][threshold]
            detail_rows.append({"filename": filename, "condition": photo["condition"], "threshold": threshold,
                                "tp": len(expected & predicted), "fp": len(predicted - expected),
                                "fn": len(expected - predicted), "ground_truth": json.dumps(sorted(expected), ensure_ascii=False),
                                "predicted": json.dumps(sorted(predicted), ensure_ascii=False)})

    bootstrap_rows = bootstrap_intervals(per_photo, category_by_name)
    for row in bootstrap_rows:
        all_row = next(x for x in summary_rows if x["threshold"] == row["threshold"]
                       and x["cakupan"] == "Keseluruhan" and x["kategori"] == "semua")
        avoid_row = next(x for x in summary_rows if x["threshold"] == row["threshold"]
                         and x["cakupan"] == "Keseluruhan" and x["kategori"] == "hindari")
        all_row.update({"f1_ci95_low": row["f1_ci95_low"], "f1_ci95_high": row["f1_ci95_high"]})
        avoid_row.update({"recall_ci95_low": row["hindari_recall_ci95_low"],
                          "recall_ci95_high": row["hindari_recall_ci95_high"]})

    total_rows = [row for row in summary_rows if row["cakupan"] == "Keseluruhan" and row["kategori"] == "semua"]
    best_f1 = max(row["f1"] for row in total_rows)
    near_best = [row for row in total_rows if best_f1 - row["f1"] < 0.01]
    # Use category-specific Hindari recall for the tie-break, not total recall.
    selected = max(near_best, key=lambda row: (
        next(x["recall"] for x in summary_rows if x["threshold"] == row["threshold"]
             and x["cakupan"] == "Keseluruhan" and x["kategori"] == "hindari"),
        row["f1"], -row["threshold"]))
    selected_hindari_recall = next(row["recall"] for row in summary_rows if row["threshold"] == selected["threshold"]
                                   and row["cakupan"] == "Keseluruhan" and row["kategori"] == "hindari")
    max_f1_thresholds = [row["threshold"] for row in total_rows if row["f1"] == best_f1]
    near_text = [row["threshold"] for row in near_best]
    if len(near_best) == 1:
        selection_reason = f"F1 tertinggi unik ({best_f1:.4f})."
    elif selected["f1"] < best_f1:
        selection_reason = (f"F1 threshold {selected['threshold']}={selected['f1']:.4f} berjarak <0,01 dari "
                            f"maksimum {best_f1:.4f}; recall Hindari tertinggi di antara {near_text} "
                            f"({selected_hindari_recall:.4f}).")
    else:
        selection_reason = (f"Threshold {selected['threshold']} memiliki F1 maksimum {best_f1:.4f}; "
                            f"recall Hindari {selected_hindari_recall:.4f} dipakai sebagai pemecah seri.")

    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_path = OCR_CACHE.parent / "runtime.json"
    cache_runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig")) if runtime_path.exists() else {}
    if args.ocr_ablation_detail:
        cache_runtime = {"source": str(args.ocr_ablation_detail), "max_ocr_width": args.max_ocr_width,
                         "adaptive_threshold": args.adaptive_threshold == "on"}
    metadata = {
        "label": "provisional_ablation_grid" if args.ocr_ablation_detail else "provisional_cached_ocr",
        "split": "calibration_only",
        "n_photos": 40,
        "thresholds": list(THRESHOLDS),
        "bootstrap": {"iterations": BOOTSTRAP_ITERATIONS, "seed": BOOTSTRAP_SEED,
                      "confidence_level": 0.95, "resampling_unit": "foto"},
        "threshold_selection": {"rule": "F1 total maksimum; jika selisih < 0.01, pilih recall Hindari lebih tinggi",
                                "selected_threshold": selected["threshold"], "reason": selection_reason,
                                "f1": selected["f1"], "hindari_recall": selected_hindari_recall},
        "cache_directory": (str(OCR_CACHE.relative_to(ROOT)) if not args.ocr_ablation_detail else None),
        "ocr_cache_runtime": cache_runtime,
        "ocr_configuration": {
            "max_ocr_width": cache_runtime.get("max_ocr_width", 2000),
            "adaptive_threshold": cache_runtime.get("adaptive_threshold", False),
            "preprocessing": ("selected row from OCR ablation detail; no OCR rerun" if args.ocr_ablation_detail
                              else "grayscale -> Gaussian blur -> CLAHE -> deskew (cached raw detections)"),
        },
        "ground_truth": str(gt_path.relative_to(ROOT)),
        "ground_truth_sha256": hashlib.sha256(gt_path.read_bytes()).hexdigest(),
        "kb_path": str(KB.relative_to(ROOT)),
        "kb_sha256": hashlib.sha256(KB.read_bytes()).hexdigest(),
        "blocked_pairs_path": "backend/app/matching/chemical_pair_blocks.json",
        "blocked_pairs_sha256": hashlib.sha256(
            (ROOT / "backend/app/matching/chemical_pair_blocks.json").read_bytes()
        ).hexdigest(),
        "ocr_ablation_detail_path": (str(args.ocr_ablation_detail) if args.ocr_ablation_detail else None),
        "ocr_ablation_detail_sha256": (hashlib.sha256(args.ocr_ablation_detail.read_bytes()).hexdigest()
                                        if args.ocr_ablation_detail else None),
        "commit_hash": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
    }
    (output_dir / "provisional_run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output_dir / "grid_summary.csv", summary_rows)
    write_csv(output_dir / "grid_detail.csv", detail_rows)
    write_csv(output_dir / "bootstrap_ci.csv", bootstrap_rows)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for category, label in (("semua", "Keseluruhan"), ("aman", "Aman"), ("perhatian", "Perlu Perhatian"), ("hindari", "Hindari")):
        points = [r for r in summary_rows if r["cakupan"] == "Keseluruhan" and r["kategori"] == category]
        ax.plot([r["threshold"] for r in points], [r["f1"] for r in points], marker="o", label=label, linewidth=2)
    ax.set_xlabel("Threshold")
    ax.set_ylabel("F1")
    ax.set_xticks(THRESHOLDS)
    ax.set_ylim(0, 1)
    ax.grid(axis="y", alpha=.25)
    ax.legend(frameon=False)
    fig.savefig(output_dir / "provisional_gambar_f1_threshold.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Threshold terpilih: {selected['threshold']} - {selection_reason}")
    print(f"Selesai: {output_dir}; 40 foto kalibrasi, threshold {THRESHOLDS}; "
          f"bootstrap {BOOTSTRAP_ITERATIONS}x (seed {BOOTSTRAP_SEED}); tidak ada split evaluasi diproses.")


if __name__ == "__main__":
    main()
