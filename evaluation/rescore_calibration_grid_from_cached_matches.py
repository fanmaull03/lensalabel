"""Re-score saved calibration matches against a revised calibration GT.

This script does not run OCR or the matcher. It is valid only when the saved
per-photo/per-threshold predictions were made with the current matcher, KB,
blocked-pair data, and exactly the same OCR text/configuration. Provenance for
each source is recorded beside the re-scored grid.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from run_calibration_grid_v2 import (  # noqa: E402
    BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED, CATEGORIES, THRESHOLDS,
    bootstrap_intervals, flatten_kb, metrics, write_csv,
)

DEFAULT_GT = ROOT / "dataset/ground_truth/calibration_ingredients_gt_v2_2.json"
OCR_DETAIL = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv"
KB_PATH = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
BLOCKS_PATH = ROOT / "backend/app/matching/chemical_pair_blocks.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_names(value: str) -> set[str]:
    return set(json.loads(value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt-json", type=Path, default=DEFAULT_GT)
    parser.add_argument("--source-suffix", default="gt_v2_1")
    parser.add_argument("--output-suffix", default="gt_v2_2")
    args = parser.parse_args()
    gt_path = args.gt_json if args.gt_json.is_absolute() else ROOT / args.gt_json
    gt = json.loads(gt_path.read_text(encoding="utf-8-sig"))
    kb_doc = json.loads(KB_PATH.read_text(encoding="utf-8-sig"))
    category_by_name = {str(row["standard_name"]): str(row["category"]).casefold()
                        for row in kb_doc["ingredients"]}
    if len(gt) != 40:
        raise RuntimeError("Rescoring hanya menerima 40 foto kalibrasi.")
    ocr_rows = read_rows(OCR_DETAIL)
    ocr_by_config = {}
    for row in ocr_rows:
        ocr_by_config.setdefault(row["config_key"], {})[row["filename"]] = row["ocr_text"]
    thresholds = tuple(THRESHOLDS)
    split_rows = read_rows(ROOT / "evaluation/splits/calibration_set.csv")
    conditions = {r["filename"]: r["category"] for r in split_rows}
    if set(gt) != set(conditions):
        raise RuntimeError("GT v2.2 dan split kalibrasi tidak identik.")

    for width in (1000, 1500, 2000):
        for adaptive in ("off", "on"):
            config_key = f"width_{width}_adaptive_{adaptive}"
            source_dir = ROOT / f"evaluation/results/grid_{config_key}_{args.source_suffix}"
            source_path = source_dir / "grid_detail.csv"
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            rows = read_rows(source_path)
            if len(rows) != 40 * len(thresholds):
                raise RuntimeError(f"Detail sumber tidak lengkap: {source_path}")
            if set(ocr_by_config.get(config_key, {})) != set(conditions):
                raise RuntimeError(f"OCR detail bukan 40 foto unik untuk {config_key}")

            # Verify that the exact OCR text used to produce the source predictions
            # matches the clean Colab detail, rather than trusting a path label.
            source_meta = json.loads((source_dir / "provisional_run_metadata.json").read_text(encoding="utf-8-sig"))
            source_ocr_path = Path(source_meta["ocr_cache_runtime"]["source"])
            if not source_ocr_path.is_absolute():
                source_ocr_path = ROOT / source_ocr_path
            source_ocr = {r["filename"]: r["ocr_text"] for r in read_rows(source_ocr_path)
                          if r.get("config_key") == config_key}
            if source_ocr != ocr_by_config[config_key]:
                raise RuntimeError(f"Teks OCR sumber berbeda dari detail Colab bersih untuk {config_key}")

            predictions: dict[str, dict[int, set[str]]] = {name: {} for name in conditions}
            for row in rows:
                predictions[row["filename"]][int(row["threshold"])] = parse_names(row["predicted"])
            if any(set(by_threshold) != set(thresholds) for by_threshold in predictions.values()):
                raise RuntimeError(f"Prediksi threshold tidak lengkap untuk {config_key}")

            per_photo = {}
            detail_rows = []
            for filename, condition in conditions.items():
                expected = {str(i["standard_name"]) for i in gt[filename].get("ingredients", [])}
                per_photo[filename] = {"condition": condition, "gt": expected,
                                       "predictions": predictions[filename]}
                for threshold in thresholds:
                    predicted = predictions[filename][threshold]
                    tp, fp, fn = len(expected & predicted), len(predicted - expected), len(expected - predicted)
                    precision, recall, f1 = metrics(tp, fp, fn)
                    detail_rows.append({"filename": filename, "condition": condition, "threshold": threshold,
                                        "category": condition, "tp": tp, "fp": fp, "fn": fn,
                                        "precision": precision, "recall": recall, "f1": f1,
                                        "ground_truth": json.dumps(sorted(expected), ensure_ascii=False),
                                        "predicted": json.dumps(sorted(predicted), ensure_ascii=False),
                                        "false_positive": json.dumps(sorted(predicted - expected), ensure_ascii=False),
                                        "false_negative": json.dumps(sorted(expected - predicted), ensure_ascii=False)})

            summary_rows = []
            scopes = [("Keseluruhan", lambda _row: True),
                      ("Datar", lambda row: row["condition"] == "datar"),
                      ("Melengkung", lambda row: row["condition"] == "melengkung")]
            for threshold in thresholds:
                for scope_name, include in scopes:
                    chosen = [row for row in per_photo.values() if include(row)]
                    for category in ("semua", *CATEGORIES):
                        tp = fp = fn = 0
                        for photo in chosen:
                            expected = photo["gt"]
                            predicted = photo["predictions"][threshold]
                            in_cat = ((lambda _name: True) if category == "semua" else
                                      (lambda name, c=category: category_by_name.get(name) == c))
                            tp += sum(in_cat(name) for name in expected & predicted)
                            fp += sum(in_cat(name) for name in predicted - expected)
                            fn += sum(in_cat(name) for name in expected - predicted)
                        precision, recall, f1 = metrics(tp, fp, fn)
                        summary_rows.append({"threshold": threshold, "cakupan": scope_name,
                                             "kategori": category, "foto": len(chosen), "tp": tp,
                                             "fp": fp, "fn": fn, "precision": precision,
                                             "recall": recall, "f1": f1})

            bootstrap_rows = bootstrap_intervals(per_photo, category_by_name)
            for boot in bootstrap_rows:
                overall = next(r for r in summary_rows if r["threshold"] == boot["threshold"]
                               and r["cakupan"] == "Keseluruhan" and r["kategori"] == "semua")
                avoid = next(r for r in summary_rows if r["threshold"] == boot["threshold"]
                             and r["cakupan"] == "Keseluruhan" and r["kategori"] == "hindari")
                overall.update({"f1_ci95_low": boot["f1_ci95_low"], "f1_ci95_high": boot["f1_ci95_high"]})
                avoid.update({"recall_ci95_low": boot["hindari_recall_ci95_low"],
                              "recall_ci95_high": boot["hindari_recall_ci95_high"]})

            overall_rows = [r for r in summary_rows if r["cakupan"] == "Keseluruhan" and r["kategori"] == "semua"]
            max_f1 = max(r["f1"] for r in overall_rows)
            near = [r for r in overall_rows if max_f1 - r["f1"] < 0.01]
            def avoid_recall(row):
                return next(r["recall"] for r in summary_rows if r["threshold"] == row["threshold"]
                            and r["cakupan"] == "Keseluruhan" and r["kategori"] == "hindari")
            selected = max(near, key=lambda r: (avoid_recall(r), r["f1"], -r["threshold"]))
            selected_recall = avoid_recall(selected)
            if len(near) == 1:
                reason = f"F1 tertinggi unik ({max_f1:.4f})."
            elif selected["f1"] < max_f1:
                reason = (f"F1 {selected['f1']:.4f} berjarak <0,01 dari maksimum {max_f1:.4f}; "
                          f"recall Hindari tertinggi ({selected_recall:.4f}).")
            else:
                reason = f"F1 maksimum {max_f1:.4f}; recall Hindari {selected_recall:.4f} memecah seri."

            output_dir = ROOT / f"evaluation/results/grid_{config_key}_{args.output_suffix}"
            output_dir.mkdir(parents=True, exist_ok=True)
            write_csv(output_dir / "grid_summary.csv", summary_rows)
            write_csv(output_dir / "grid_detail.csv", detail_rows)
            write_csv(output_dir / "bootstrap_ci.csv", bootstrap_rows)
            metadata = {
                "label": "gt_v2_2_rescored_from_verified_cached_matches",
                "split": "calibration_only", "n_photos": 40, "thresholds": list(thresholds),
                "threshold_selection": {"rule": "F1 total maksimum; jika selisih < 0.01, pilih recall Hindari lebih tinggi",
                                        "selected_threshold": selected["threshold"], "f1": selected["f1"],
                                        "hindari_recall": selected_recall, "reason": reason},
                "ground_truth": str(gt_path.relative_to(ROOT)), "ground_truth_sha256": sha(gt_path),
                "kb_path": str(KB_PATH.relative_to(ROOT)), "kb_sha256": sha(KB_PATH),
                "blocked_pairs_path": str(BLOCKS_PATH.relative_to(ROOT)), "blocked_pairs_sha256": sha(BLOCKS_PATH),
                "ocr_ablation_detail_path": str(OCR_DETAIL.relative_to(ROOT)), "ocr_ablation_detail_sha256": sha(OCR_DETAIL),
                "ocr_ablation_text_verified_equal_to_source": True,
                "source_grid_detail": str(source_path.relative_to(ROOT)), "source_grid_detail_sha256": sha(source_path),
                "source_grid_metadata_sha256": sha(source_dir / "provisional_run_metadata.json"),
                "source_ocr_detail_path": str(source_ocr_path), "source_ocr_detail_sha256": sha(source_ocr_path),
                "match_predictions_reused": True,
                "matcher_source_sha256": sha(ROOT / "backend/app/matching/fuzzy_matcher.py"),
                "matcher_pair_blocks_source_sha256": sha(ROOT / "backend/app/matching/pair_blocks.py"),
                "commit_hash": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                               capture_output=True, text=True).stdout.strip(),
                "ocr_configuration": {"config_key": config_key, "max_ocr_width": width,
                                      "adaptive_threshold": adaptive == "on",
                                      "runtime": {k: ocr_rows[0].get(k) for k in
                                                  ("easyocr_version", "torch_version", "opencv_headless_version", "opencv_runtime_version")}},
                "bootstrap": {"iterations": BOOTSTRAP_ITERATIONS, "seed": BOOTSTRAP_SEED,
                              "confidence_level": 0.95, "resampling_unit": "foto"},
            }
            (output_dir / "provisional_run_metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{config_key}: threshold={selected['threshold']} F1={selected['f1']:.4f} "
                  f"R_hindari={selected_recall:.4f}; outputs={output_dir.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
