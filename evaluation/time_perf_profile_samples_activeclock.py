"""Re-time the six established OCR texts with the perf branch and a sleep-safe clock."""
from __future__ import annotations

import csv
import ctypes
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/post_eval_supplement"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


def active_elapsed() -> float:
    if os.name == "nt":
        counter = ctypes.c_ulonglong()
        query = ctypes.windll.kernel32.QueryUnbiasedInterruptTime
        query.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        query.restype = ctypes.c_int
        if query(ctypes.byref(counter)):
            return counter.value / 10_000_000
    return time.perf_counter()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    from app.classifier.rule_based import classify_product
    from app.matching.fuzzy_matcher import match_token_many
    from app.tokenizer.tokenizer import extract_composition_section, tokenize
    from evaluation.frozen_config import load_config
    from evaluation.run_evaluate_160_parallel import flatten_kb, init_worker

    config = load_config(require_frozen=True)
    kb, _, ids = flatten_kb(json.loads((ROOT / config["kb_path"]).read_text(encoding="utf-8-sig")))
    weights = {k: float(v) for k, v in config["weights"].items()}
    exponent = float(config["length_penalty"]["exponent"])
    init_worker(kb, weights, float(config["threshold"]), exponent, ids)
    old = read_csv(ROOT / "evaluation/results/post_evaluation/matcher_timing_profile_samples.csv")
    eval_rows = {r["filename"]: r for r in read_csv(ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv")}
    cal_rows = {r["filename"]: r for r in read_csv(ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv")
                if r.get("config_key") == "width_1500_adaptive_off"}
    rows = []
    for prior in old:
        source = eval_rows if prior["source_split"] == "eval" else cal_rows
        data = source[prior["filename"]]
        text = data["ocr_text"]
        tokens = tokenize(extract_composition_section(text))
        start = active_elapsed()
        matches = [m for token in tokens for m in match_token_many(
            token, kb, weights=weights, threshold=float(config["threshold"]), shared_heads=True,
            length_penalty_exponent=exponent)]
        classify_product(matches)
        current = active_elapsed() - start
        prior_seconds = float(prior["matcher_seconds"])
        rows.append({"filename": prior["filename"], "source_split": prior["source_split"],
                     "condition": prior["condition"], "old_serial_seconds": prior_seconds,
                     "optimized_active_seconds": current,
                     "speedup_ratio": prior_seconds / current if current else "",
                     "elapsed_clock": "QueryUnbiasedInterruptTime"})
        print(f"{prior['filename']}: {prior_seconds:.2f}s -> {current:.2f}s", flush=True)
    write_csv(OUT / "perf_matcher_profile_comparison_activeclock.csv", rows)
    ratios = [float(row["speedup_ratio"]) for row in rows]
    report = {"n": len(rows), "median_speedup": statistics.median(ratios),
              "mean_speedup": statistics.mean(ratios), "min_speedup": min(ratios),
              "max_speedup": max(ratios), "elapsed_clock": "QueryUnbiasedInterruptTime",
              "same_saved_ocr_texts_as_prior_profile": True}
    (OUT / "perf_matcher_profile_comparison_activeclock.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
