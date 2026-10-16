"""Compare complete matcher predictions without running OCR."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import sys
from time import perf_counter

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.classifier.rule_based import classify_product
from app.matching import fuzzy_matcher, fuzzy_matcher_optimized
from app.tokenizer.tokenizer import extract_composition_section, tokenize

WEIGHTS = {"levenshtein": 1 / 3, "jaro_winkler": 1 / 3, "ngram": 1 / 3}
KB = None


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def init_worker(path):
    global KB
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    KB = [{"ingredient_id": row["id"], "standard_name": row["standard_name"],
           "category": row["category"], "name_variant": variant}
          for row in source["ingredients"]
          for variant in [row["standard_name"], *row["synonyms"]]]


def predict(module, raw):
    matches = [match for token in tokenize(extract_composition_section(raw))
               for match in module.match_token_many(
                   token, KB, weights=WEIGHTS, threshold=75, shared_heads=True,
                   secondary_min_score=None, secondary_full_coverage=False,
                   length_penalty_exponent=0.8)]
    return {"matches": [asdict(match) for match in matches],
            "classification": classify_product(matches)}


def compare(task):
    kind, name, condition, raw = task
    begin = perf_counter()
    old = predict(fuzzy_matcher, raw)
    frozen_seconds = perf_counter() - begin
    begin = perf_counter()
    new = predict(fuzzy_matcher_optimized, raw)
    optimized_seconds = perf_counter() - begin
    equal = old == new
    return {"kind": kind, "filename": name, "condition": condition,
            "identical": equal, "frozen_seconds": frozen_seconds,
            "optimized_seconds": optimized_seconds,
            "frozen": None if equal else old, "optimized": None if equal else new}


def synthetic(rows, count):
    rng = random.Random(42)
    fragments = [(r["category"], part.strip()) for r in rows
                 for part in re.split(r"[,;]", r["ground_truth_text"])
                 if 2 <= len(part.split()) <= 5]
    if not fragments:
        raise ValueError("Fragmen transkrip kosong")
    heads = ["Dinatrium Inosinat dan Guanilat", "Perisa Sintetik dan Alami",
             "Penguat Rasa (Dinatrium Inosinat, Guanilat)"]
    result = []
    seen = set()
    attempt = 0
    while len(result) < count:
        i = attempt
        attempt += 1
        condition, source = rng.choice(fragments)
        mode = i % 7
        if mode == 0:
            pos = rng.randrange(len(source))
            text = source[:pos] + rng.choice("abcdefghijklmnopqrstuvwxyz") + source[pos:]
        elif mode == 1 and len(source) > 3:
            pos = rng.randrange(1, len(source) - 1)
            text = source[:pos] + source[pos + 1:]
        elif mode == 2 and len(source) > 3:
            pos = rng.randrange(1, len(source) - 1)
            text = source[:pos] + source[pos + 1] + source[pos] + source[pos + 2:]
        elif mode == 3:
            text = " ".join(source.split()[:-1]) or source
        elif mode == 4:
            # Dua butir daftar yang semula dipisahkan koma, lalu komanya hilang.
            text = source + " " + rng.choice(fragments)[1]
        elif mode == 5:
            text = rng.choice(["tanpa ", "bebas ", "tidak mengandung "]) + source
        else:
            text = rng.choice(heads) + ", " + source
        if text in seen:
            continue
        seen.add(text)
        result.append(("synthetic", f"synthetic_{len(result):04d}", condition, text))
    return result


def p95(values):
    values = sorted(values)
    pos = .95 * (len(values) - 1)
    low = int(pos)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (pos - low)


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["kind"], row["condition"])].append(row)
        groups[(row["kind"], "total")].append(row)
    summary = {}
    for (kind, condition), group in groups.items():
        entry = {"count": len(group), "identical": sum(x["identical"] for x in group)}
        for mode in ("frozen", "optimized"):
            values = [x[f"{mode}_seconds"] for x in group]
            entry[mode] = {"mean": statistics.mean(values),
                           "median": statistics.median(values), "p95": p95(values),
                           "sum": sum(values)}
        summary[f"{kind}/{condition}"] = entry
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--synthetic-count", type=int, default=2000)
    parser.add_argument("--cached-equivalence-report", type=Path,
                        help="Reuse a completed 200-photo full-prediction comparison only if both module hashes match")
    args = parser.parse_args()
    root = args.research_root
    evaluation = csv_rows(root / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv")
    calibration = [r for r in csv_rows(root / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv")
                   if r["config_key"] == "width_1500_adaptive_off"]
    if len(evaluation) != 160 or len(calibration) != 40:
        raise ValueError("Cache OCR harus berisi tepat 160 + 40 foto")
    tasks = []
    reused = None
    if args.cached_equivalence_report:
        prior = json.loads(args.cached_equivalence_report.read_text(encoding="utf-8"))
        provenance = json.loads((args.cached_equivalence_report.parent /
                                 "perf_matcher_equivalence_200.json").read_text(encoding="utf-8"))
        inputs = {
            "evaluation_ocr_csv": "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv",
            "calibration_ocr_detail": "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv",
            "evaluation_prediction_cache": "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl",
            "calibration_prediction_cache": "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl",
            "config_frozen.json": "evaluation/config_frozen.json",
            "kb": "evaluation/results/kb_v2_phase2/kb_v2_review.json",
            "pair_blocks": "backend/app/matching/chemical_pair_blocks.json",
        }
        for key, relative in inputs.items():
            actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            if actual != provenance["sha256"][key]:
                raise ValueError(f"Input uji lama berubah: {relative}")
        frozen_hash = hashlib.sha256(Path(fuzzy_matcher.__file__).read_bytes()).hexdigest()
        optimized_hash = hashlib.sha256(Path(fuzzy_matcher_optimized.__file__).read_bytes()).hexdigest()
        if (prior.get("photos") != 200 or prior.get("full_prediction_identical") != 200
                or prior.get("frozen_matcher_sha256") != frozen_hash
                or prior.get("local_matcher_sha256") != optimized_hash):
            raise ValueError("Laporan 200 foto tidak cocok dengan kedua modul byte-identik")
        reused = {"report": str(args.cached_equivalence_report),
                  "frozen_hash": frozen_hash, "optimized_hash": optimized_hash,
                  "full_prediction_identical": 200}
    else:
        tasks = [("cached_ocr", r["filename"], r["category"], r["ocr_text"]) for r in evaluation]
        tasks += [("cached_ocr", r["filename"], r["condition"], r["ocr_text"]) for r in calibration]
    tasks += synthetic(csv_rows(root / "dataset/ground_truth/transcripts.csv"), args.synthetic_count)
    kb = BACKEND / "app/db/knowledge_base_v2_deploy.json"
    results = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker,
                             initargs=(str(kb),)) as pool:
        futures = [pool.submit(compare, task) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 20 == 0:
                print(f"{len(results)}/{len(tasks)} compared", flush=True)
    results.sort(key=lambda row: (row["kind"], row["filename"]))
    differences = [r for r in results if not r["identical"]]
    report = {"seed": 42, "cached_ocr": 200, "synthetic": args.synthetic_count,
              "reused_cached_ocr_evidence": reused,
              "identical": len(results) - len(differences) + (200 if reused else 0),
              "total": len(results) + (200 if reused else 0),
              "summary": summarize(results), "differences": differences}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "differences"},
                     ensure_ascii=False), flush=True)
    if differences:
        print(json.dumps(differences, ensure_ascii=False), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
