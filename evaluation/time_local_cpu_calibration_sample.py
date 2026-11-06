"""Measure local CPU OCR+serial matcher on a fixed seed-42 calibration sample."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import os
import platform
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/post_eval_supplement"
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
os.environ["EASYOCR_GPU"] = "0"


def active_elapsed() -> float:
    """Windows unbiased interrupt time excludes suspend/hibernate intervals."""
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
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    import cv2
    import easyocr
    import torch
    from app.classifier.rule_based import classify_product
    from app.matching.fuzzy_matcher import match_token_many
    from app.ocr.reader import extract_text, get_reader
    from app.preprocessing.pipeline import preprocess
    from app.tokenizer.tokenizer import extract_composition_section, tokenize
    from evaluation.run_evaluate_160_parallel import flatten_kb
    from evaluation.frozen_config import load_config

    config = load_config(require_frozen=True)
    split = read_csv(ROOT / "evaluation/splits/calibration_set.csv")
    rng = random.Random(42)
    sampled = []
    for condition in ("datar", "melengkung"):
        candidates = [r for r in split if r["category"] == condition]
        sampled.extend({**r, "condition": condition} for r in rng.sample(candidates, 10))
    # Stable row order makes reruns easy to compare.
    sampled.sort(key=lambda r: (r["condition"], r["filename"]))

    kb_doc = json.loads((ROOT / config["kb_path"]).read_text(encoding="utf-8-sig"))
    flat_kb, _, _ = flatten_kb(kb_doc)
    weights = {k: float(v) for k, v in config["weights"].items()}
    threshold = float(config["threshold"])
    exponent = float(config["length_penalty"]["exponent"])
    cv2.setNumThreads(cv2.getNumThreads())
    torch_threads = torch.get_num_threads()
    interop_threads = torch.get_num_interop_threads()
    cv_threads = cv2.getNumThreads()

    reader_start = active_elapsed()
    get_reader()
    reader_init_s = active_elapsed() - reader_start
    rows = []
    for index, photo in enumerate(sampled, start=1):
        image_path = ROOT / "dataset/raw_photos" / photo["condition"] / photo["filename"]
        cpu0 = time.process_time()
        t0 = active_elapsed()
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        read_s = active_elapsed() - t0
        read_cpu = time.process_time() - cpu0
        cpu1 = time.process_time()
        t1 = active_elapsed()
        prepared = preprocess(image)
        prep_s = active_elapsed() - t1
        prep_cpu = time.process_time() - cpu1
        cpu2 = time.process_time()
        t2 = active_elapsed()
        raw_ocr = extract_text(prepared, max_width=1500)
        ocr_s = active_elapsed() - t2
        ocr_cpu = time.process_time() - cpu2
        cpu3 = time.process_time()
        t3 = active_elapsed()
        composition = extract_composition_section(raw_ocr)
        tokens = tokenize(composition)
        extract_token_s = active_elapsed() - t3
        extract_token_cpu = time.process_time() - cpu3
        cpu4 = time.process_time()
        t4 = active_elapsed()
        matches = [m for token in tokens for m in match_token_many(
            token, flat_kb, weights=weights, threshold=threshold, shared_heads=True,
            length_penalty_exponent=exponent)]
        matcher_s = active_elapsed() - t4
        matcher_cpu = time.process_time() - cpu4
        cpu5 = time.process_time()
        t5 = active_elapsed()
        classify_product(matches)
        classifier_s = active_elapsed() - t5
        classifier_cpu = time.process_time() - cpu5
        total = read_s + prep_s + ocr_s + extract_token_s + matcher_s + classifier_s
        rows.append({"filename": photo["filename"], "condition": photo["condition"],
                     "image_read_seconds": read_s, "preprocess_seconds": prep_s,
                     "ocr_seconds": ocr_s, "composition_and_tokenize_seconds": extract_token_s,
                     "matcher_seconds": matcher_s, "classifier_seconds": classifier_s,
                     "total_seconds": total, "ocr_chars": len(raw_ocr), "ocr_text_sha256": hashlib.sha256(raw_ocr.encode("utf-8")).hexdigest(),
                     "token_count": len(tokens), "image_read_cpu_seconds": read_cpu,
                     "preprocess_cpu_seconds": prep_cpu, "ocr_cpu_seconds": ocr_cpu,
                     "composition_tokenize_cpu_seconds": extract_token_cpu,
                     "matcher_cpu_seconds": matcher_cpu, "classifier_cpu_seconds": classifier_cpu})
        print(f"[{index}/20] {photo['filename']} OCR={ocr_s:.2f}s matcher={matcher_s:.2f}s total={total:.2f}s", flush=True)

    write_csv(OUT / "local_cpu_timing_sample20_seed42_activeclock.csv", rows)
    summary = []
    for condition in ("datar", "melengkung"):
        items = [r for r in rows if r["condition"] == condition]
        for metric in ("ocr_seconds", "matcher_seconds", "total_seconds"):
            vals = [float(r[metric]) for r in items]
            summary.append({"condition": condition, "metric": metric, "n": len(vals),
                            "mean_seconds": sum(vals) / len(vals), "median_seconds": __import__("statistics").median(vals),
                            "min_seconds": min(vals), "max_seconds": max(vals)})
    write_csv(OUT / "local_cpu_timing_summary_seed42_activeclock.csv", summary)
    env = {"python": platform.python_version(), "python_implementation": platform.python_implementation(),
           "platform": platform.platform(), "processor": platform.processor() or "Intel Core i3-1005G1 (Windows registry)",
           "logical_cpu_count": os.cpu_count(), "torch_device": "CPU", "torch_threads": torch_threads,
           "torch_interop_threads": interop_threads, "opencv_threads": cv_threads,
           "easyocr": easyocr.__version__, "torch": torch.__version__, "opencv": cv2.__version__,
           "opencv_module_path": cv2.__file__, "width": 1500, "adaptive_threshold": False,
           "reader_initialization_seconds_once": reader_init_s,
           "elapsed_clock": "QueryUnbiasedInterruptTime (Windows active elapsed, excludes sleep/hibernate; perf_counter fallback)",
           "selection": "10 datar + 10 melengkung, random.Random(42), sorted within condition",
           "heavy_process_check": "manual pre-run CPU sampling; see timing_summary.md"}
    (OUT / "local_cpu_timing_environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(env, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
