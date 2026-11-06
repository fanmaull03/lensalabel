"""Compare tagged frozen matcher vs current branch on the same 200 OCR texts."""
from __future__ import annotations

import concurrent.futures
import csv
import ctypes
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from evaluation import run_evaluate_160_parallel as wrapper  # noqa: E402
from evaluation.frozen_config import load_config  # noqa: E402

OUT = ROOT / "evaluation/results/post_eval_supplement"
_BENCH: dict[str, Any] = {}


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_cache(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {row["filename"]: row["prediction"] for row in rows[1:] if row.get("record_type") == "photo"}


def core_signature(prediction: dict) -> tuple:
    entries = sorted((int(item["ingredient_id"]), str(item["standard_name"]), str(item["category"]))
                     for item in prediction.get("entries", []))
    return tuple(entries), str(prediction.get("verdict", ""))


def init(kb: list[dict], weights: dict, threshold: float, exponent: float, ids: dict) -> None:
    global _BENCH
    import app.matching.fuzzy_matcher as matcher
    # Same pure memoization cache size as the frozen parallel wrapper.
    from functools import lru_cache
    matcher._bigrams = lru_cache(maxsize=100_000)(matcher._bigrams.__wrapped__ if hasattr(matcher._bigrams, "__wrapped__") else matcher._bigrams)
    matcher._many_score = lru_cache(maxsize=500_000)(matcher._many_score.__wrapped__ if hasattr(matcher._many_score, "__wrapped__") else matcher._many_score)
    matcher._best_fragment = lru_cache(maxsize=100_000)(matcher._best_fragment.__wrapped__ if hasattr(matcher._best_fragment, "__wrapped__") else matcher._best_fragment)
    _BENCH.update(kb=kb, weights=weights, threshold=threshold, exponent=exponent, ids=ids, matcher=matcher)


def predict(task: tuple[str, str, str]) -> dict:
    from app.classifier.rule_based import classify_product
    from app.tokenizer.tokenizer import extract_composition_section, tokenize
    filename, condition, text = task
    tokens = tokenize(extract_composition_section(text))
    start = active_elapsed()
    matches = [match for token in tokens for match in _BENCH["matcher"].match_token_many(
        token, _BENCH["kb"], weights=_BENCH["weights"], threshold=_BENCH["threshold"],
        shared_heads=True, length_penalty_exponent=_BENCH["exponent"])]
    classified = classify_product(matches)
    elapsed = active_elapsed() - start
    prediction = wrapper._serialize_prediction(matches, classified, _BENCH["ids"])
    # Round-trip so the in-memory tuple span has the same JSON list form as cache.
    prediction = json.loads(json.dumps(prediction, ensure_ascii=False))
    return {"filename": filename, "condition": condition, "prediction": prediction,
            "matcher_and_classifier_seconds": elapsed}


def run(tasks: list[tuple[str, str, str]], kb: list[dict], weights: dict,
        threshold: float, exponent: float, ids: dict, workers: int) -> list[dict]:
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, initializer=init,
            initargs=(kb, weights, threshold, exponent, ids)) as pool:
        return list(pool.map(predict, tasks, chunksize=1))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    config = load_config(require_frozen=True)
    kb_doc = json.loads((ROOT / config["kb_path"]).read_text(encoding="utf-8-sig"))
    kb, _, ids = wrapper.flatten_kb(kb_doc)
    weights = {k: float(v) for k, v in config["weights"].items()}
    threshold = float(config["threshold"])
    exponent = float(config["length_penalty"]["exponent"])
    eval_ocr = read_csv(ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv")
    cal_ocr = [r for r in read_csv(ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv")
               if r.get("config_key") == "width_1500_adaptive_off"]
    if len(eval_ocr) != 160 or len(cal_ocr) != 40:
        raise RuntimeError("Benchmark perlu 160 OCR evaluasi dan 40 OCR kalibrasi 1500/OFF")
    tasks = [(r["filename"], r["category"], r["ocr_text"]) for r in eval_ocr]
    tasks += [(r["filename"], r["condition"], r["ocr_text"]) for r in cal_ocr]
    expected = load_cache(ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl")
    expected.update(load_cache(ROOT / "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl"))
    if len(expected) != 200:
        raise RuntimeError(f"Cache prediksi bukan 200 foto: {len(expected)}")
    workers = min(4, os.cpu_count() or 1)
    start = active_elapsed()
    rows = run(tasks, kb, weights, threshold, exponent, ids, workers)
    wall = active_elapsed() - start
    diffs = [r["filename"] for r in rows
             if core_signature(r["prediction"]) != core_signature(expected[r["filename"]])]
    print(f"optimized: elapsed={wall:.2f}s, mismatches={len(diffs)}/{len(rows)}", flush=True)
    if diffs:
        (OUT / "perf_optimized_mismatches.json").write_text(json.dumps(diffs, indent=2), encoding="utf-8")
        raise RuntimeError(f"Optimasi tidak identik terhadap cache; foto pertama {diffs[:3]}")
    summaries, per_photo = [], []
    for condition in ("datar", "melengkung", "gabungan"):
        group = rows if condition == "gabungan" else [r for r in rows if r["condition"] == condition]
        times = [float(r["matcher_and_classifier_seconds"]) for r in group]
        summaries.append({"condition": condition, "n": len(times),
                          "mean_seconds": statistics.mean(times), "median_seconds": statistics.median(times),
                          "min_seconds": min(times), "max_seconds": max(times)})
    per_photo = [{"filename": r["filename"], "condition": r["condition"],
                  "matcher_and_classifier_seconds": r["matcher_and_classifier_seconds"]} for r in rows]
    write_csv(OUT / "perf_matcher_benchmark_200_per_photo.csv", per_photo)
    write_csv(OUT / "perf_matcher_benchmark_200_summary.csv", summaries)

    old_profiles = read_csv(ROOT / "evaluation/results/post_evaluation/matcher_timing_profile_samples.csv")
    measured = {r["filename"]: r for r in rows}
    profile_rows = []
    for old in old_profiles:
        current = measured.get(old["filename"])
        if current is None:
            continue
        old_s = float(old["matcher_seconds"])
        new_s = float(current["matcher_and_classifier_seconds"])
        profile_rows.append({"filename": old["filename"], "source_split": old["source_split"],
                             "condition": old["condition"], "old_serial_seconds": old_s,
                             "optimized_serial_worker_seconds": new_s,
                             "speedup_ratio": old_s / new_s if new_s else ""})
    write_csv(OUT / "perf_matcher_profile_comparison.csv", profile_rows)
    speedups = [float(r["speedup_ratio"]) for r in profile_rows]
    report = {"passed": True, "photos": 200, "threshold": threshold, "workers": workers,
              "optimized_wall_seconds": wall,
              "optimized_sum_worker_seconds": sum(float(r["matcher_and_classifier_seconds"]) for r in rows),
              "prediction_mismatches": 0,
              "comparison": "(ingredient_id, standard_name, category) tuples plus product verdict vs committed frozen cache",
              "elapsed_clock": "QueryUnbiasedInterruptTime on Windows; excludes suspend/hibernate",
              "sha256": {
                  "config_frozen.json": sha256(ROOT / "evaluation/config_frozen.json"),
                  "matcher_branch": sha256(ROOT / "backend/app/matching/fuzzy_matcher.py"),
                  "kb": sha256(ROOT / config["kb_path"]),
                  "pair_blocks": sha256(ROOT / "backend/app/matching/chemical_pair_blocks.json"),
                  "evaluation_ocr_csv": sha256(ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv"),
                  "calibration_ocr_detail": sha256(ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv"),
                  "evaluation_prediction_cache": sha256(ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"),
                  "calibration_prediction_cache": sha256(ROOT / "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl"),
              },
              "profile_samples": len(profile_rows),
              "median_speedup_on_previous_serial_profiles": statistics.median(speedups) if speedups else None,
              "mean_speedup_on_previous_serial_profiles": statistics.mean(speedups) if speedups else None,
              "note": "Per-photo worker time includes matcher and classifier; prior profile times are from the same saved OCR text sources.",
              "baseline_samples_source": "evaluation/results/post_evaluation/matcher_timing_profile_samples.csv"}
    (OUT / "perf_matcher_equivalence_200.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
