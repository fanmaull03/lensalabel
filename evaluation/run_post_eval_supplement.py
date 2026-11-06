"""Additional descriptive analyses on the frozen OCR/prediction caches.

No frozen inputs are written. All new tables go to results/post_eval_supplement.
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/post_eval_supplement"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation import evaluate_160_metrics as metrics  # noqa: E402
from evaluation import run_evaluate_160_parallel as wrapper  # noqa: E402
from evaluation.frozen_config import load_config  # noqa: E402

CONFIG = load_config(require_frozen=True)
GT_PATH = ROOT / CONFIG["evaluation_gt_path"]
OCR_PATH = ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv"
PRED_PATH = ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"
DETAIL_PATH = ROOT / "evaluation/results/evaluation_ocr/evaluation_metrics_detail.csv"
KB_PATH = ROOT / CONFIG["kb_path"]
LABELS = ("aman", "perhatian", "hindari")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ["status"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_jsonl(path: Path) -> tuple[dict, dict[str, dict]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return rows[0], {row["filename"]: row for row in rows[1:] if row.get("record_type") == "photo"}


def f1_for_label(truth: list[str], pred: list[str], label: str) -> float:
    tp = sum(a == label and b == label for a, b in zip(truth, pred))
    fp = sum(a != label and b == label for a, b in zip(truth, pred))
    fn = sum(a == label and b != label for a, b in zip(truth, pred))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def macro_f1(truth: list[str], pred: list[str]) -> float:
    return statistics.mean(f1_for_label(truth, pred, label) for label in LABELS)


def kappa(truth: list[str], pred: list[str]) -> float:
    n = len(truth)
    observed = sum(a == b for a, b in zip(truth, pred)) / n if n else 0.0
    ct, cp = Counter(truth), Counter(pred)
    expected = sum(ct[x] * cp[x] for x in LABELS) / (n * n) if n else 0.0
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def binary_pr(truth: list[str], pred: list[str], label: str) -> tuple[float, float]:
    tp = sum(a == label and b == label for a, b in zip(truth, pred))
    fp = sum(a != label and b == label for a, b in zip(truth, pred))
    fn = sum(a == label and b != label for a, b in zip(truth, pred))
    return tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0


def verdict_summary() -> dict:
    _, predictions = load_jsonl(PRED_PATH)
    gt = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    names = sorted(gt)
    truth = [metrics.strongest_category({str(x.get("category", "aman")).casefold()
             for x in gt[name].get("ingredients", [])}) for name in names]
    status = [predictions[name]["prediction"]["classification"]["verdict"] for name in names]
    system = ["perhatian" if x in {"perlu_verifikasi", "tidak_terbaca"} else x for x in status]
    baseline = ["hindari"] * len(names)
    rng = np.random.default_rng(42)
    indices = rng.integers(0, len(names), size=(1000, len(names)))
    metrics_by_row = {
        "baseline_akurasi": [], "baseline_macro_f1": [], "baseline_kappa": [],
        "sistem_precision_hindari": [], "sistem_recall_hindari": [],
    }
    for index in indices:
        t = [truth[int(i)] for i in index]
        b = [baseline[int(i)] for i in index]
        s = [system[int(i)] for i in index]
        metrics_by_row["baseline_akurasi"].append(sum(a == b0 for a, b0 in zip(t, b)) / len(t))
        metrics_by_row["baseline_macro_f1"].append(macro_f1(t, b))
        metrics_by_row["baseline_kappa"].append(kappa(t, b))
        p, r = binary_pr(t, s, "hindari")
        metrics_by_row["sistem_precision_hindari"].append(p)
        metrics_by_row["sistem_recall_hindari"].append(r)

    p0, r0 = binary_pr(truth, baseline, "hindari")
    p1, r1 = binary_pr(truth, system, "hindari")
    point = {
        "baseline_akurasi": sum(a == b for a, b in zip(truth, baseline)) / len(names),
        "baseline_macro_f1": macro_f1(truth, baseline),
        "baseline_kappa": kappa(truth, baseline),
        "sistem_precision_hindari": p1,
        "sistem_recall_hindari": r1,
    }
    rows = []
    for key, value in point.items():
        samples = metrics_by_row[key]
        rows.append({"metrik": key, "nilai": value,
                     "ci95_bawah": float(np.quantile(samples, .025)),
                     "ci95_atas": float(np.quantile(samples, .975)),
                     "resampling": 1000, "seed": 42, "unit": "foto"})
    n_hindari = sum(x == "hindari" for x in truth)
    dangerous_safe = sum(a == "hindari" and b == "aman" for a, b in zip(truth, status))
    cp_upper = 1 - 0.05 ** (1 / n_hindari) if dangerous_safe == 0 else None
    rows.append({"metrik": "batas_atas_clopper_pearson_gt_hindari_dinyatakan_aman",
                 "nilai": dangerous_safe / n_hindari, "ci95_bawah": 0.0,
                 "ci95_atas": cp_upper, "resampling": "exact one-sided", "seed": "-",
                 "unit": f"kejadian/{n_hindari}"})
    write_csv(OUT / "verdict_baseline_and_hindari_ci.csv", rows)
    return {"items": rows, "n_hindari": n_hindari, "system_hindari_precision": p1,
            "system_hindari_recall": r1, "dangerous_gt_hindari_system_aman": dangerous_safe,
            "clopper_pearson_upper_95": cp_upper, "truth": dict(Counter(truth))}


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)


def best_entry_candidate(text: str, target_variants: list[str], matcher, weights: dict,
                         exponent: float) -> dict:
    """Find top KB-entry score/span over all word windows; diagnostic only."""
    best = {"score": -1.0, "token": "", "window": "", "start": -1, "end": -1,
            "variant": "", "entry_id": None, "standard_name": ""}
    for token in text.split("\n"):
        # The canonical tokenizer may combine OCR fragments. We therefore also
        # score each non-empty normalized line and whitespace window within it.
        word_matches = list(re.finditer(r"\S+", token))
        if not word_matches:
            continue
        for variant, entry in target_variants:
            count = len(variant.split())
            widths = {w for w in (count - 1, count, count + 1) if w >= 1}
            fragments = [(token, 0, len(token))]
            for width in widths:
                for offset in range(len(word_matches) - width + 1):
                    selected = word_matches[offset:offset + width]
                    fragments.append((" ".join(w.group(0) for w in selected), selected[0].start(), selected[-1].end()))
            for window, start, end in fragments:
                if matcher.is_forbidden_pair(window, variant):
                    continue
                score = matcher.composite_score(window, variant, weights, exponent)
                if score > best["score"]:
                    best = {"score": score, "token": token, "window": window, "start": start,
                            "end": end, "variant": variant, "entry_id": entry["ingredient_id"],
                            "standard_name": entry["standard_name"]}
    return best


def fn_candidate_analysis() -> dict:
    from app.matching import fuzzy_matcher as matcher
    from app.tokenizer.tokenizer import extract_composition_section, tokenize

    config = CONFIG
    kb_doc = json.loads(KB_PATH.read_text(encoding="utf-8-sig"))
    flat, categories, ids = wrapper.flatten_kb(kb_doc)
    by_id: dict[int, list[tuple[str, dict]]] = defaultdict(list)
    for entry in flat:
        by_id[int(entry["ingredient_id"])].append((str(entry["name_variant"]), entry))
    gt = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    _, prediction_rows = load_jsonl(PRED_PATH)
    ocr_rows = {r["filename"]: r for r in read_csv(OCR_PATH)}
    candidate_rows = []
    for filename in sorted(gt):
        raw = ocr_rows[filename]["ocr_text"]
        composition = extract_composition_section(raw)
        tokens = tokenize(composition)
        predicted_matches = prediction_rows[filename]["prediction"].get("matches", [])
        accepted = [m for m in predicted_matches if m.get("matched")]
        for item in gt[filename].get("ingredients", []):
            target_id = int(item.get("ingredient_id", -1))
            target_name = str(item["standard_name"])
            if any(m.get("standard_name") == target_name for m in accepted):
                continue
            candidates = best_entry_candidate("\n".join(tokens), by_id.get(target_id, []), matcher,
                                              {k: float(v) for k, v in config["weights"].items()},
                                              float(config["length_penalty"]["exponent"]))
            # Compare the diagnostic candidate span to accepted matcher spans
            # in the same token. The decision rules are ordered and exclusive.
            same = []
            covers = []
            if candidates["score"] >= float(config["threshold"]):
                for match in accepted:
                    if str(match.get("token", "")) != candidates["token"]:
                        continue
                    left, right = int(match.get("span_start") or 0), int(match.get("span_end") or 0)
                    if left == candidates["start"] and right == candidates["end"]:
                        same.append(match)
                    elif left <= candidates["start"] and candidates["end"] <= right and (left, right) != (candidates["start"], candidates["end"]):
                        covers.append(match)
            if candidates["score"] < 0:
                cause = "d_lain_tidak_ada_kandidat_yang_diperbolehkan"
            elif candidates["score"] < float(config["threshold"]):
                cause = "a_di_bawah_threshold_75"
            elif same:
                cause = "b_di_span_sama_kalah_ke_entri_lain"
            elif covers:
                cause = "c_ditutup_span_lebih_panjang"
            else:
                cause = "d_lain"
            cause_group = "d_lain" if cause.startswith("d_lain") else cause
            candidate_rows.append({"condition": gt[filename].get("category", ""), "filename": filename,
                                   "standard_name": target_name, "category": item.get("category", ""),
                                   "cause": cause_group, "subcause": cause, "best_score": candidates["score"],
                                   "best_variant": candidates["variant"], "candidate_window": candidates["window"],
                                   "candidate_token": candidates["token"],
                                   "selected_competing_entries": " | ".join(str(x.get("standard_name")) for x in (same or covers)),
                                   "threshold": config["threshold"]})
    write_csv(OUT / "fn_candidate_not_selected_by_condition.csv", [
        {"condition": condition, "cause": cause,
         "count": sum(x["condition"] == condition and x["cause"] == cause for x in candidate_rows),
         "total_fn": sum(x["condition"] == condition for x in candidate_rows)}
        for condition in ("datar", "melengkung")
        for cause in ("a_di_bawah_threshold_75", "b_di_span_sama_kalah_ke_entri_lain", "c_ditutup_span_lebih_panjang", "d_lain")])
    write_csv(OUT / "fn_candidate_not_selected_detail.csv", candidate_rows)
    quartiles = []
    for condition in ("datar", "melengkung"):
        vals = [float(x["best_score"]) for x in candidate_rows if x["condition"] == condition and x["cause"] == "a_di_bawah_threshold_75"]
        quartiles.append({"condition": condition, "n": len(vals),
                          "min": min(vals) if vals else "", "q1": float(np.quantile(vals, .25)) if vals else "",
                          "median": float(np.quantile(vals, .5)) if vals else "",
                          "q3": float(np.quantile(vals, .75)) if vals else "",
                          "max": max(vals) if vals else ""})
    write_csv(OUT / "fn_below_threshold_score_quartiles.csv", quartiles)
    return {"counts": Counter((x["condition"], x["cause"]) for x in candidate_rows), "quartiles": quartiles,
            "total_fn": len(candidate_rows)}


def fp_sample_analysis() -> dict:
    """Sample 60 legacy residual FP events and label only evidence-backed causes."""
    from app.tokenizer.tokenizer import extract_composition_section
    _, predictions = load_jsonl(PRED_PATH)
    gt = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    ocr = {r["filename"]: r["ocr_text"] for r in read_csv(OCR_PATH)}
    kb, _, _ = wrapper.flatten_kb(json.loads(KB_PATH.read_text(encoding="utf-8-sig")))
    variants: dict[str, list[str]] = defaultdict(list)
    for row in kb:
        variants[str(row["standard_name"])].append(str(row["name_variant"]))
    events = [r for r in read_csv(ROOT / "evaluation/results/post_evaluation/error_events_fp_classified.csv")
              if r.get("cause") == "lain_tidak_terklasifikasi"]
    rng = random.Random(42)
    sample = rng.sample(events, min(60, len(events)))
    out_rows = []
    for row in sample:
        fn, predicted = row["filename"], row["predicted_ingredient"]
        pred_matches = [m for m in predictions[fn]["prediction"].get("matches", [])
                        if m.get("matched") and m.get("standard_name") == predicted]
        best = max(pred_matches, key=lambda m: float(m.get("score", 0)), default={})
        window = str(best.get("matched_window", row.get("matched_window", "")))
        token = str(best.get("token", row.get("token", "")))
        full_text = ocr[fn]
        comp_text = extract_composition_section(full_text)
        gt_items = gt[fn].get("ingredients", [])
        matched_variant = str(best.get("matched_variant", ""))
        # Candidate long-span containment is evaluated before other causes.
        covering = [str(x.get("matched_variant", x.get("standard_name", ""))) for x in gt_items
                    if window and window.casefold() != str(x.get("matched_variant", "")).casefold()
                    and window.casefold() in str(x.get("matched_variant", "")).casefold()]
        normalized_target = re.sub(r"\W+", " ", matched_variant.casefold()).strip()
        normalized_text = re.sub(r"\W+", " ", comp_text.casefold()).strip()
        out_of_list_re = re.compile(
            r"takaran saji|serving size|informasi nilai gizi|nutrition facts|energi total|persen akg|"
            r"%\s*akg|disarankan|dianjurkan|tidak dikonsumsi|jangan dikonsumsi|ibu menyusui|"
            r"ibu hamil|anak di bawah|setelah dibuka|sebaiknya|simpan|disimpan|jauhkan dari|"
            r"hindari sinar|klaim|gluten free|bebas gluten|tanpa susu", re.I)
        if covering:
            cause = "subspan_tercakup_GT_R1_or_specific"
            basis = "matched window adalah substring varian keputusan GT yang lebih panjang"
            covering_gt = " | ".join(covering)
        elif out_of_list_re.search(token):
            cause = "teks_anjuran_klaim_atau_gizi_terbawa_ekstraksi"
            basis = "token OCR sekitar hit memuat penanda gizi, anjuran, penyimpanan, klaim atau batas konsumsi"
            covering_gt = ""
        elif normalized_target and f" {normalized_target} " in f" {normalized_text} ":
            cause = "teks_komposisi_ada_tetapi_entri_tidak_ada_di_GT"
            basis = "varian KB tercantum utuh di OCR, tetapi entri tidak ada pada GT foto"
            covering_gt = ""
        elif float(best.get("score", row.get("score", 100)) or 0) < 100:
            cause = "kemiripan_string"
            basis = "match diterima dengan skor komposit di bawah 100"
            covering_gt = ""
        elif re.search(r"\b[A-Z]{3,}\b", token) or re.search(r"\b(?:merek|brand|rasa|varian)\b", token, re.I):
            cause = "kata_nama_merek"
            basis = "token berisi rentetan kapital/kata penanda nama atau varian produk"
            covering_gt = ""
        else:
            cause = "belum_tertentu_dari_bukti"
            basis = "bukti OCR/GT tidak cukup untuk satu hipotesis secara deterministik"
            covering_gt = ""
        # OCR excerpt around exact matched window when possible.
        at = full_text.casefold().find(window.casefold()) if window else -1
        excerpt = full_text[max(0, at - 70):at + len(window) + 90] if at >= 0 else token[:220]
        from rapidfuzz import fuzz
        gt_variants = [(str(x.get("matched_variant", x.get("standard_name", ""))),
                        str(x.get("standard_name", ""))) for x in gt_items]
        nearest_gt = max(gt_variants, key=lambda x: fuzz.ratio(window.casefold(), x[0].casefold()), default=("", ""))
        out_rows.append({"filename": fn, "condition": row["condition"], "cause": cause,
                         "predicted_ingredient": predicted, "matched_variant": matched_variant,
                         "matched_window": window, "score": best.get("score", row.get("score", "")),
                         "ocr_excerpt": excerpt.replace("\n", " "),
                         "closest_gt_ingredient": nearest_gt[1], "closest_gt_variant": nearest_gt[0],
                         "gt_variant_that_covers_window": covering_gt,
                         "evidence_rule": basis})
    write_csv(OUT / "fp_lain_sample60_seed42.csv", out_rows)
    counts = Counter(x["cause"] for x in out_rows)
    summary = [{"cause": cause, "n": n, "sample_n": len(out_rows), "proportion": n / max(1, len(out_rows))}
               for cause, n in counts.items()]
    write_csv(OUT / "fp_lain_sample60_causes.csv", summary)
    examples = []
    for cause in counts:
        examples.extend({**x, "example_rank_within_cause": i + 1}
                        for i, x in enumerate([r for r in out_rows if r["cause"] == cause][:3]))
    write_csv(OUT / "fp_lain_sample60_examples_3_per_cause.csv", examples)
    return {"sample_n": len(out_rows), "counts": counts, "sample": out_rows}


def sensitivity_worker(task: tuple[str, str, str]) -> dict[int, dict]:
    """Reuse per-worker score caches across all thresholds for one OCR text."""
    results = {}
    for threshold in (65, 70, 75, 80, 85):
        wrapper._WORKER["threshold"] = float(threshold)
        results[threshold] = wrapper.worker_predict(task)
    return results


def threshold_sensitivity() -> list[dict]:
    """Re-match OCR texts at five thresholds, reusing pure score caches per worker."""
    from concurrent.futures import ProcessPoolExecutor

    split = read_csv(ROOT / "evaluation/splits/evaluation_set.csv")
    ocr_rows = {r["filename"]: r for r in read_csv(OCR_PATH)}
    transcripts = {r["filename"]: r["ground_truth_text"]
                   for r in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    tasks = [(r["filename"], r["category"], ocr_rows[r["filename"]]["ocr_text"]) for r in split]
    gt_doc = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    kb_doc = json.loads(KB_PATH.read_text(encoding="utf-8-sig"))
    flat, categories, ids = wrapper.flatten_kb(kb_doc)
    exponent = float(CONFIG["length_penalty"]["exponent"])
    weights = {k: float(v) for k, v in CONFIG["weights"].items()}
    predictions_by_threshold = {t: [] for t in (65, 70, 75, 80, 85)}
    with ProcessPoolExecutor(max_workers=min(4, __import__("os").cpu_count() or 1),
                             initializer=wrapper.init_worker,
                             initargs=(flat, weights, 75.0, exponent, ids)) as pool:
        for done, result in enumerate(pool.map(sensitivity_worker, tasks, chunksize=1), start=1):
            for threshold, row in result.items():
                predictions_by_threshold[threshold].append(row)
            if done % 10 == 0 or done == len(tasks):
                print(f"sensitivitas: {done}/160 foto selesai untuk 5 threshold", flush=True)

    summaries = []
    expected_75 = load_jsonl(PRED_PATH)[1]
    for threshold, prediction_rows in predictions_by_threshold.items():
        predicted = {r["filename"]: r for r in prediction_rows}
        if threshold == 75:
            mismatches = [name for name, row in predicted.items()
                          if row["prediction"] != expected_75[name]["prediction"]]
            if mismatches:
                raise RuntimeError(f"Rematch threshold 75 tidak identik pada {len(mismatches)} foto")
        records = wrapper.make_metric_records(split, predicted, gt_doc, categories, transcripts,
                                              {name: {"ocr_text": ocr_rows[name]["ocr_text"], "ocr_runtime_seconds": 0}
                                               for name in ocr_rows})
        p, r, f = metrics.metric_triplet(records, "ingredient")
        hindari_recall = metrics.verdict_stats(records, "hindari")[1]
        summaries.append({"threshold": threshold, "ingredient_precision": p, "ingredient_recall": r,
                          "ingredient_f1": f, "verdict_recall_hindari": hindari_recall,
                          "photos": len(records), "purpose": "analisis sensitivitas pasca-evaluasi; threshold beku 75 tidak berubah"})
    write_csv(OUT / "threshold_sensitivity_65_85.csv", summaries)
    return summaries


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = verdict_summary()
    print("Verdict summary:", json.dumps({k: v for k, v in baseline.items() if k != "items"}, ensure_ascii=False))
    fn = fn_candidate_analysis()
    print("FN candidate classes:", fn["counts"])
    print("FN below-threshold score quartiles:", fn["quartiles"])
    fp = fp_sample_analysis()
    print("FP other sample cause counts:", fp["counts"])
    # Threshold rematching is intentionally an explicit second-stage command.
    print("Analisis deskriptif selesai. Jalankan dengan --threshold-sensitivity untuk rematch sensitivitas.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-sensitivity", action="store_true")
    args = parser.parse_args()
    if args.threshold_sensitivity:
        OUT.mkdir(parents=True, exist_ok=True)
        print(json.dumps(threshold_sensitivity(), ensure_ascii=False, indent=2))
    else:
        main()
