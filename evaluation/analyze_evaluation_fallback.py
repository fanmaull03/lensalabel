"""Analyze frozen evaluation fallback frequencies and cached ingredient metrics.

This reads saved OCR text, frozen predictions and frozen GT only. It never
calls OCR, the matcher, or the evaluation prediction pipeline.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.tokenizer.tokenizer import OPEN_MARKERS, _find_closing_marker, _find_marker  # noqa: E402

GT_PATH = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
OCR_PATH = ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv"
CACHE_PATH = ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"
SPLIT_PATH = ROOT / "evaluation/splits/evaluation_set.csv"


def bootstrap(records: list[dict], iterations: int = 1000, seed: int = 42):
    def aggregate(selected):
        tp = fp = fn = 0
        for row in selected:
            tp += len(row["gt"] & row["pred"])
            fp += len(row["pred"] - row["gt"])
            fn += len(row["gt"] - row["pred"])
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return p, r, 2 * p * r / (p + r) if p + r else 0.0, tp, fp, fn

    point = aggregate(records) if records else (0., 0., 0., 0, 0, 0)
    if not records:
        return point, [(None, None)] * 3
    rng = np.random.default_rng(seed)
    samples = np.empty((iterations, 3), dtype=float)
    for i in range(iterations):
        selected = [records[j] for j in rng.integers(0, len(records), size=len(records))]
        vals = aggregate(selected)[:3]
        samples[i] = vals
    cis = [(float(np.quantile(samples[:, j], .025)), float(np.quantile(samples[:, j], .975))) for j in range(3)]
    return point, cis


def load_records():
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    with SPLIT_PATH.open(encoding="utf-8-sig", newline="") as f: split = {r["filename"]: r["category"] for r in csv.DictReader(f)}
    with OCR_PATH.open(encoding="utf-8-sig", newline="") as f: ocr = {r["filename"]: r["ocr_text"] for r in csv.DictReader(f)}
    cache_lines = [json.loads(s) for s in CACHE_PATH.read_text(encoding="utf-8").splitlines() if s.strip()]
    pred = {r["filename"]: r["prediction"] for r in cache_lines if r.get("record_type") == "photo"}
    if not (set(gt) == set(split) == set(ocr) == set(pred)):
        raise ValueError("GT, split, OCR cache, dan prediksi cache tidak cocok.")
    records = []
    for filename in sorted(gt):
        text = ocr[filename]
        words = text.split()
        open_idx = _find_marker(words, OPEN_MARKERS)
        close_idx = _find_closing_marker(words, start=open_idx + 1) if open_idx is not None else None
        prediction = pred[filename]
        gt_names = {x["standard_name"] for x in gt[filename].get("ingredients", [])}
        pred_names = {x["standard_name"] for x in prediction.get("entries", []) if x.get("standard_name")}
        records.append({"filename": filename, "condition": "datar" if split[filename] == "datar" else "melengkung",
                        "open_missing": open_idx is None, "close_missing": open_idx is not None and close_idx is None,
                        "gt": gt_names, "pred": pred_names})
    return records


def analyze(records: list[dict]):
    rows = []
    for fallback_type, flag in (("penanda_pembuka_tidak_ditemukan", "open_missing"), ("penanda_penutup_tidak_ditemukan", "close_missing")):
        for condition in ("keseluruhan", "datar", "melengkung"):
            condition_records = records if condition == "keseluruhan" else [r for r in records if r["condition"] == condition]
            # Closing fallback is only defined for records whose opening marker exists.
            if flag == "close_missing": condition_records = [r for r in condition_records if not r["open_missing"]]
            for fallback in (True, False):
                group = [r for r in condition_records if r[flag] == fallback]
                point, ci = bootstrap(group)
                p, rec, f1, tp, fp, fn = point
                rows.append({"jenis_fallback": fallback_type, "kondisi": condition,
                             "kelompok": "fallback" if fallback else "non_fallback", "jumlah_foto": len(group),
                             "jumlah_denominator": len(condition_records), "TP": tp, "FP": fp, "FN": fn,
                             "precision": p, "precision_ci95_bawah": ci[0][0], "precision_ci95_atas": ci[0][1],
                             "recall": rec, "recall_ci95_bawah": ci[1][0], "recall_ci95_atas": ci[1][1],
                             "f1": f1, "f1_ci95_bawah": ci[2][0], "f1_ci95_atas": ci[2][1],
                             "resampling": 1000, "seed": 42, "interpretasi": "deskriptif (kelompok <20 foto)" if len(group) < 20 else "bootstrap per foto"})
    freq = []
    for condition in ("keseluruhan", "datar", "melengkung"):
        group = records if condition == "keseluruhan" else [r for r in records if r["condition"] == condition]
        opening = sum(r["open_missing"] for r in group)
        # For opening fallback report closing marker status only when opening existed.
        closure_eligible = [r for r in group if not r["open_missing"]]
        closing = sum(r["close_missing"] for r in closure_eligible)
        freq.append({"kondisi": condition, "foto": len(group), "pembuka_tidak_ditemukan": opening,
                     "pembuka_ditemukan": len(group) - opening, "penutup_tidak_ditemukan_dari_pembuka_ditemukan": closing,
                     "penutup_ditemukan_dari_pembuka_ditemukan": len(closure_eligible) - closing})
    return rows, freq


def main():
    p = argparse.ArgumentParser(); p.add_argument("--out-dir", type=Path, default=ROOT / "evaluation/results/expert_interview"); args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows, freq = analyze(load_records())
    for name, data in (("fallback_metrics_by_group.csv", rows), ("fallback_frequency.csv", freq)):
        with (args.out_dir / name).open("w", encoding="utf-8-sig", newline="") as f:
            fields = list(dict.fromkeys(k for r in data for k in r)); w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(data)
    (args.out_dir / "fallback_analysis.json").write_text(json.dumps({"frequencies": freq, "metrics": rows, "source_note": "Cached OCR and cached frozen predictions; no OCR or matcher execution."}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"frequencies": freq, "metrics": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
