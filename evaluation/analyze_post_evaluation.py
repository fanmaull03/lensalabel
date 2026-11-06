"""Summarize saved 160-photo outputs without rerunning OCR or predictions.

The error-cause labels are deterministic evidence-based heuristics. They are
descriptive audit categories, not matcher changes or claims of causal proof.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results/evaluation_ocr"
OUT = ROOT / "evaluation/results/post_evaluation"
ASSETS = ROOT / "evaluation/results/chapter4"
GT_PATH = ROOT / "evaluation/ground_truth/evaluation_gt_kb_v2_final.json"
OCR_PATH = RESULTS / "evaluation_ocr_160.csv"
PRED_PATH = RESULTS / "evaluation_predictions_cache.jsonl"
DETAIL_PATH = RESULTS / "evaluation_metrics_detail.csv"
SUMMARY_PATH = RESULTS / "evaluation_metrics_summary.csv"
LABELS = ("aman", "perhatian", "hindari")
PRIORITY = {"aman": 0, "perhatian": 1, "hindari": 2}


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def excerpt(text: str, needle: str = "", width: int = 180) -> str:
    if not text:
        return ""
    start = 0
    if needle:
        hit = text.casefold().find(needle.casefold())
        if hit >= 0:
            start = max(0, hit - width // 3)
        else:
            nwords = max(1, len(needle.split()))
            words = text.split()
            best_score, best_start = -1.0, 0
            for i in range(len(words)):
                candidate = " ".join(words[i:i + nwords + 2])
                score = fuzz.partial_ratio(needle.casefold(), candidate.casefold())
                if score > best_score:
                    best_score, best_start = score, i
            start = max(0, len(" ".join(text.split()[:best_start])) - width // 3)
    return text[start:start + width].replace("\n", " ").strip()


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    return sum(a == b for a, b in zip(y_true, y_pred)) / max(1, len(y_true))


def class_f1(y_true: list[str], y_pred: list[str], label: str) -> float:
    tp = sum(a == label and b == label for a, b in zip(y_true, y_pred))
    fp = sum(a != label and b == label for a, b in zip(y_true, y_pred))
    fn = sum(a == label and b != label for a, b in zip(y_true, y_pred))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    return statistics.mean(class_f1(y_true, y_pred, label) for label in LABELS)


def cohen_kappa(y_true: list[str], y_pred: list[str]) -> float:
    n = len(y_true)
    if not n:
        return 0.0
    observed = accuracy(y_true, y_pred)
    true_counts, pred_counts = Counter(y_true), Counter(y_pred)
    expected = sum(true_counts[k] * pred_counts[k] for k in LABELS) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def bootstrap_stats(y_true: list[str], y_pred: list[str], iterations: int = 1000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(y_true)
    base_n = Counter(y_true)
    majority = max(base_n, key=lambda x: (base_n[x], -LABELS.index(x)))
    values = {"majority_baseline_accuracy": [], "system_accuracy": [], "system_macro_f1": [], "system_cohen_kappa": []}
    resamples = rng.integers(0, n, size=(iterations, n))
    for indices in resamples:
        truth = [y_true[int(i)] for i in indices]
        pred = [y_pred[int(i)] for i in indices]
        values["majority_baseline_accuracy"].append(accuracy(truth, [majority] * n))
        values["system_accuracy"].append(accuracy(truth, pred))
        values["system_macro_f1"].append(macro_f1(truth, pred))
        values["system_cohen_kappa"].append(cohen_kappa(truth, pred))
    result = {"majority_class": majority, "majority_baseline_accuracy": accuracy(y_true, [majority] * n),
              "system_accuracy": accuracy(y_true, y_pred), "system_macro_f1": macro_f1(y_true, y_pred),
              "system_cohen_kappa": cohen_kappa(y_true, y_pred), "bootstrap_iterations": iterations,
              "seed": seed, "confidence": 0.95, "unit": "photo"}
    for name, samples in values.items():
        result[name + "_ci95"] = [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))]
    return result


def load_prediction_cache() -> dict[str, dict]:
    predictions = {}
    with PRED_PATH.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("record_type") == "photo":
                predictions[row["filename"]] = row["prediction"]
    return predictions


def load_kb_variants() -> tuple[dict[str, str], dict[str, list[str]]]:
    config = json.loads((ROOT / "evaluation/config_frozen.json").read_text(encoding="utf-8-sig"))
    data = json.loads((ROOT / config["kb_path"]).read_text(encoding="utf-8-sig"))
    entries = data.get("ingredients", []) if isinstance(data, dict) else data
    categories, variants = {}, defaultdict(list)
    for item in entries:
        name = str(item.get("standard_name", ""))
        if not name:
            continue
        categories[name] = str(item.get("category", "")).casefold()
        variants[name].extend([name, *[str(x) for x in item.get("synonyms", [])]])
        for key in ("variants", "name_variants", "english_synonyms", "indonesian_synonyms"):
            value = item.get(key, [])
            if isinstance(value, str):
                variants[name].append(value)
            elif isinstance(value, list):
                variants[name].extend(map(str, value))
    return categories, variants


def classify_fp(filename: str, predicted_name: str, prediction: dict, gt_items: list[dict], raw: str,
                composition: str, opening_missing: bool, categories: dict[str, str]) -> tuple[str, dict, str]:
    matches = [m for m in prediction.get("matches", []) if m.get("matched") and m.get("standard_name") == predicted_name]
    match = max(matches, key=lambda m: float(m.get("score", 0)), default={})
    token = str(match.get("token", match.get("matched_window", "")))
    window = str(match.get("matched_window", ""))
    surrounding = (token + " " + window).casefold()
    nutrition_re = re.compile(r"takaran saji|serving size|informasi nilai gizi|nutrition facts|energi total|kalori|per sajian|persen akg|%\s*akg|lemak total|karbohidrat total", re.I)
    claim_re = re.compile(r"gluten\s*free|bebas gluten|bebas susu|tanpa susu|non[- ]?dairy|no preservatives|klaim", re.I)
    allergen_re = re.compile(r"mengandung|alergen|may contain|contains|dapat mengandung", re.I)
    if nutrition_re.search(surrounding) or (opening_missing and (nutrition_re.search(raw) or claim_re.search(raw))):
        cause = "teks_luar_komposisi"
    elif allergen_re.search(surrounding):
        cause = "pernyataan_mengandung_atau_alergen"
    else:
        same_category_variants = []
        pred_category = categories.get(predicted_name, "")
        for item in gt_items:
            gt_name = str(item.get("standard_name", ""))
            if gt_name == predicted_name or str(item.get("category", "")).casefold() != pred_category:
                continue
            variant = str(item.get("matched_variant", ""))
            a, b = norm(window), norm(variant)
            if a and b and a != b and (a in b or b in a):
                same_category_variants.append(variant)
        if same_category_variants:
            cause = "alias_generik_vs_spesifik_kategori_sama"
        elif match and float(match.get("score", 100)) < 100:
            cause = "kemiripan_string_salah_entri"
        else:
            cause = "lain_tidak_terklasifikasi"
    context = excerpt(composition, token or window)
    evidence = {"matched_window": window, "score": match.get("score", ""), "token": token,
                "same_category_gt_variant": "|".join(same_category_variants) if 'same_category_variants' in locals() else ""}
    return cause, evidence, context


def classify_fn(filename: str, gt_item: dict, raw: str, composition: str, opening_missing: bool,
                categories: dict[str, str], variants: dict[str, list[str]], prediction: dict) -> tuple[str, float, str]:
    name = str(gt_item.get("standard_name", ""))
    variant = str(gt_item.get("matched_variant", "")) or name
    normalized_variant = norm(variant)
    aliases = [norm(x) for x in variants.get(name, []) if norm(x)]
    all_known_variants = {norm(value) for values in variants.values() for value in values if norm(value)}
    kb_gap = bool(normalized_variant and normalized_variant not in all_known_variants)
    # A close occurrence in OCR after the extractor's returned section is
    # direct evidence that the closing marker cut off the expected ingredient.
    comp_start = raw.find(composition) if composition else -1
    suffix = raw[comp_start + len(composition):] if comp_start >= 0 else ""
    suffix_score = fuzz.partial_ratio(variant, suffix) if suffix and variant else 0
    if suffix_score >= 90:
        cause = "penanda_komposisi_memotong_bahan"
    elif kb_gap:
        cause = "bahan_atau_varian_tidak_ada_di_kb"
    else:
        exact = bool(normalized_variant and normalized_variant in norm(composition))
        best_score = fuzz.partial_ratio(variant, composition) if variant and composition else 0.0
        if exact or best_score >= 75:
            cause = "ocr_terbaca_kandidat_tidak_dipilih_threshold_atau_seleksi"
        else:
            cause = "salah_baca_atau_hilang_di_ocr"
    score = max(fuzz.partial_ratio(variant, composition), suffix_score)
    context = excerpt(composition, variant)
    return cause, score, context


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.tokenizer.tokenizer import OPEN_MARKERS, _find_marker, extract_composition_section

    gt = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    transcripts = {r["filename"]: r["ground_truth_text"] for r in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    ocr_rows = {r["filename"]: r for r in read_csv(OCR_PATH)}
    detail = {r["filename"]: r for r in read_csv(DETAIL_PATH)}
    predictions = load_prediction_cache()
    categories, variants = load_kb_variants()
    filenames = sorted(gt)

    y_true, y_system = [], []
    gt_verdict_by_file, system_status_by_file = {}, {}
    for filename in filenames:
        items = gt[filename].get("ingredients", [])
        truth = max((str(x.get("category", "aman")).casefold() for x in items),
                    key=lambda c: PRIORITY.get(c, -1), default="aman")
        status = predictions[filename]["classification"]["verdict"]
        system = "perhatian" if status in {"perlu_verifikasi", "tidak_terbaca"} else status
        y_true.append(truth)
        y_system.append(system)
        gt_verdict_by_file[filename] = truth
        system_status_by_file[filename] = status
    gt_counts = Counter(y_true)
    matrix = {(a, b): 0 for a in LABELS for b in LABELS}
    for a, b in zip(y_true, y_system):
        matrix[(a, b)] += 1
    confusion_rows = [{"verdict_gt": a, "verdict_sistem_3kelas": b, "jumlah": matrix[(a, b)]}
                      for a in LABELS for b in LABELS]
    write_csv(OUT / "verdict_confusion_3x3.csv", confusion_rows)
    cross = Counter((system_status_by_file[f], gt_verdict_by_file[f]) for f in filenames)
    cross_rows = [{"status_sistem": s, "verdict_gt": g, "jumlah": cross[(s, g)]}
                  for s in ("aman", "perhatian", "hindari", "perlu_verifikasi", "tidak_terbaca") for g in LABELS]
    write_csv(OUT / "verdict_status_5x3.csv", cross_rows)
    stats = bootstrap_stats(y_true, y_system)
    stats["gt_distribution"] = {label: gt_counts[label] for label in LABELS}
    stats["system_status_distribution"] = dict(Counter(system_status_by_file.values()))
    (OUT / "verdict_quality_bootstrap.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dangerous = []
    for filename in filenames:
        if gt_verdict_by_file[filename] == "hindari" and system_status_by_file[filename] in {"perhatian", "perlu_verifikasi", "aman"}:
            dangerous.append({"filename": filename, "system_status": system_status_by_file[filename]})
    write_csv(OUT / "gt_hindari_missed_photo_names.csv", dangerous)

    opener_counts = Counter()
    ratios = defaultdict(list)
    opener_details = []
    for filename in filenames:
        raw = ocr_rows[filename]["ocr_text"]
        comp = extract_composition_section(raw)
        missing = _find_marker(raw.split(), OPEN_MARKERS) is None
        condition = gt[filename].get("category", "")
        opener_counts[condition] += int(missing)
        transcript = transcripts.get(filename, "")
        ratio = len(comp) / max(1, len(transcript))
        ratios[condition].append(ratio)
        opener_details.append({"filename": filename, "condition": condition, "opening_marker_detected": not missing,
                               "extracted_chars": len(comp), "transcript_chars": len(transcript), "length_ratio": ratio})
    extraction_rows = [{"condition": condition, "photos": len(ratios[condition]),
                        "opening_marker_not_detected": opener_counts[condition],
                        "mean_extracted_to_transcript_char_ratio": statistics.mean(ratios[condition])}
                       for condition in ("datar", "melengkung")]
    write_csv(OUT / "composition_extraction_summary.csv", extraction_rows)
    write_csv(OUT / "composition_extraction_per_photo.csv", opener_details)

    fp_events, fn_events = [], []
    for filename in filenames:
        row = detail[filename]
        pred_names = json.loads(row["pred_names"])
        gt_names = json.loads(row["gt_names"])
        fp_names, fn_names = sorted(set(pred_names) - set(gt_names)), sorted(set(gt_names) - set(pred_names))
        prediction = predictions[filename]
        raw = ocr_rows[filename]["ocr_text"]
        composition = extract_composition_section(raw)
        missing = _find_marker(raw.split(), OPEN_MARKERS) is None
        gt_items = gt[filename].get("ingredients", [])
        gt_by_name = {str(x.get("standard_name", "")): x for x in gt_items}
        for name in fp_names:
            cause, evidence, context = classify_fp(filename, name, prediction, gt_items, raw, composition, missing, categories)
            closest_gt = ""
            if evidence.get("same_category_gt_variant"):
                candidate_variant = str(evidence["same_category_gt_variant"]).split("|")[0]
                closest_gt = next((str(x.get("standard_name", "")) for x in gt_items if x.get("matched_variant") == candidate_variant), "")
            fp_events.append({"condition": gt[filename].get("category", ""), "filename": filename,
                              "cause": cause, "predicted_ingredient": name, "gt_ingredient": closest_gt,
                              "gt_ingredients_all": " | ".join(str(x.get("standard_name", "")) for x in gt_items),
                              "system_predictions_all": " | ".join(sorted(pred_names)),
                              "ocr_excerpt": context, **evidence})
        for name in fn_names:
            item = gt_by_name[name]
            cause, score, context = classify_fn(filename, item, raw, composition, missing, categories, variants, prediction)
            nearest_pred = ""
            if prediction.get("entries"):
                nearest_pred = max(prediction["entries"], key=lambda e: float(e.get("score", 0))).get("standard_name", "")
            fn_events.append({"condition": gt[filename].get("category", ""), "filename": filename,
                              "cause": cause, "gt_ingredient": name, "predicted_ingredient": nearest_pred,
                              "gt_ingredients_all": " | ".join(str(x.get("standard_name", "")) for x in gt_items),
                              "system_predictions_all": " | ".join(sorted(pred_names)),
                              "ocr_excerpt": context, "ocr_variant_similarity": round(score, 2),
                              "gt_variant": item.get("matched_variant", "")})

    cause_order = ["teks_luar_komposisi", "kemiripan_string_salah_entri", "alias_generik_vs_spesifik_kategori_sama",
                   "pernyataan_mengandung_atau_alergen", "lain_tidak_terklasifikasi"]
    fp_summary = []
    for condition in ("datar", "melengkung"):
        part = [x for x in fp_events if x["condition"] == condition]
        for cause in cause_order:
            count = sum(x["cause"] == cause for x in part)
            fp_summary.append({"jenis": "FP", "condition": condition, "cause": cause, "jumlah": count,
                               "total_kesalahan": len(part), "proporsi": count / max(1, len(part)),
                               "aturan": "heuristik berbasis matched token, konteks OCR, kesamaan variant GT, kategori, dan skor"})
    fn_cause_order = ["salah_baca_atau_hilang_di_ocr", "penanda_komposisi_memotong_bahan",
                      "bahan_atau_varian_tidak_ada_di_kb", "ocr_terbaca_kandidat_tidak_dipilih_threshold_atau_seleksi"]
    for condition in ("datar", "melengkung"):
        part = [x for x in fn_events if x["condition"] == condition]
        for cause in fn_cause_order:
            count = sum(x["cause"] == cause for x in part)
            fp_summary.append({"jenis": "FN", "condition": condition, "cause": cause, "jumlah": count,
                               "total_kesalahan": len(part), "proporsi": count / max(1, len(part)),
                               "aturan": "heuristik: truncation dibuktikan varian muncul di suffix terpotong; KB dibandingkan dengan GT; OCR dibandingkan dengan varian GT"})
    write_csv(OUT / "error_cause_summary_by_condition.csv", fp_summary)
    write_csv(OUT / "error_events_fp_classified.csv", fp_events)
    write_csv(OUT / "error_events_fn_classified.csv", fn_events)

    rng = random.Random(42)
    examples = []
    for kind, events, order in (("FP", fp_events, cause_order), ("FN", fn_events, fn_cause_order)):
        for cause in order:
            candidates = [x for x in events if x["cause"] == cause]
            rng.shuffle(candidates)
            for event in candidates[:5]:
                examples.append({"jenis": kind, "penyebab": cause, "filename": event["filename"],
                                 "condition": event["condition"], "ocr_excerpt": event["ocr_excerpt"],
                                 "gt_ingredient": event.get("gt_ingredient", ""),
                                 "predicted_ingredient": event.get("predicted_ingredient", ""),
                                 "gt_ingredients_all": event.get("gt_ingredients_all", ""),
                                 "system_predictions_all": event.get("system_predictions_all", ""),
                                 "evidence": event.get("matched_window", event.get("gt_variant", "")),
                                 "score": event.get("score", event.get("ocr_variant_similarity", ""))})
    write_csv(OUT / "error_examples_seed42.csv", examples)

    # Existing matcher profiles were timed before the full evaluation. These
    # are sampled text profiles, not per-photo timings for all 160 photos.
    profile = [
        ("eval", "datar", "datar_044.jpeg", 21.108),
        ("kalibrasi", "datar", "datar_015.jpeg", 29.000),
        ("eval", "melengkung", "melengkung_038.jpeg", 12.384),
        ("eval", "melengkung", "melengkung_097.jpeg", 130.286),
        ("kalibrasi", "melengkung", "melengkung_076.jpeg", 16.071),
        ("kalibrasi", "melengkung", "melengkung_014.jpeg", 16.034),
    ]
    timing_rows = []
    for condition in ("datar", "melengkung"):
        vals = [p[3] for p in profile if p[1] == condition]
        timing_rows.append({"measure": "matcher_serial_profile_sample", "condition": condition,
                            "n_sample": len(vals), "mean_seconds": statistics.mean(vals),
                            "median_seconds": statistics.median(vals), "min_seconds": min(vals), "max_seconds": max(vals),
                            "device": "Laptop lokal, CPU; profil teks sampel, bukan semua foto evaluasi"})
    write_csv(OUT / "matcher_timing_profile_samples.csv", [
        {"source_split": split, "condition": condition, "filename": filename, "matcher_seconds": seconds,
         "device": "Laptop lokal CPU"} for split, condition, filename, seconds in profile])
    write_csv(OUT / "matcher_timing_profile_summary.csv", timing_rows)

    # Latest available OCR timings are persisted in the 160-photo Colab CSV.
    ocr_times = [float(r["ocr_runtime_seconds"]) for r in ocr_rows.values()]
    ablation = read_csv(ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv")
    selected = [r for r in ablation if r.get("config_key") == "width_1500_adaptive_off"]
    env = json.loads((ROOT / "evaluation/results/calibration_ocr_ablation/environment_versions.json").read_text(encoding="utf-8-sig"))
    ablation_rows = []
    for condition in ("datar", "melengkung"):
        vals = [float(r["ocr_runtime_seconds"]) for r in selected if r["condition"] == condition]
        config_vals = [float(r["configuration_runtime_seconds"]) for r in selected if r["condition"] == condition]
        ablation_rows.append({"condition": condition, "photos": len(vals), "mean_ocr_seconds": statistics.mean(vals) if vals else "",
                              "mean_preprocess_plus_ocr_seconds": statistics.mean(config_vals) if config_vals else "",
                              "recorded_device": "not recorded; environment is Colab-compatible CUDA build, actual device cannot be confirmed"})
    (OUT / "timing_ocr_metadata.json").write_text(json.dumps({
        "evaluation_colab_ocr_mean_seconds_per_photo": statistics.mean(ocr_times),
        "evaluation_colab_ocr_photos": len(ocr_times), "evaluation_colab_environment": {
            "easyocr": ocr_rows[filenames[0]].get("easyocr_version", ""),
            "torch": ocr_rows[filenames[0]].get("torch_version", ""),
            "opencv": ocr_rows[filenames[0]].get("opencv_version", ""),
            "opencv_module_path": ocr_rows[filenames[0]].get("opencv_module_path", "")},
        "ablation_environment_versions": env,
        "ablation_selected_config": "width_1500_adaptive_off",
        "ablation_cpu_device_confirmed": False,
        "ablation_note": "CSV tidak mencatat cuda.is_available()/nama perangkat; angka runtimenya tidak dapat diklaim sebagai CPU lokal."}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT / "ablation_ocr_timing_by_condition.csv", ablation_rows)

    # Figures for the documented aggregate analysis.
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    mat = np.array([[matrix[(a, b)] for b in LABELS] for a in LABELS])
    ax.imshow(mat, cmap="Blues")
    ax.set_xticks(range(3), ["Aman", "Perhatian", "Hindari"])
    ax.set_yticks(range(3), ["Aman", "Perhatian", "Hindari"])
    ax.set_xlabel("Verdict sistem")
    ax.set_ylabel("Verdict GT")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, str(mat[i, j]), ha="center", va="center")
    fig.tight_layout()
    fig.savefig(ASSETS / "gambar_4_12_verdict_confusion_160.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    chart_rows = [r for r in fp_summary if r["jenis"] in {"FP", "FN"}]
    causes = ["teks_luar_komposisi", "kemiripan_string_salah_entri", "alias_generik_vs_spesifik_kategori_sama",
              "pernyataan_mengandung_atau_alergen", "lain_tidak_terklasifikasi", "salah_baca_atau_hilang_di_ocr",
              "penanda_komposisi_memotong_bahan", "bahan_atau_varian_tidak_ada_di_kb",
              "ocr_terbaca_kandidat_tidak_dipilih_threshold_atau_seleksi"]
    short = ["Teks luar", "Kemiripan string", "Alias generik", "Alergen", "Lain", "OCR hilang/salah baca",
             "Marker memotong", "Cakupan KB", "Threshold/seleksi"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, kind in zip(axes, ("FP", "FN")):
        rows = [r for r in chart_rows if r["jenis"] == kind]
        labels = short[:5] if kind == "FP" else short[5:]
        use_causes = causes[:5] if kind == "FP" else causes[5:]
        y = np.arange(len(use_causes))
        for offset, cond, color in [(-.18, "datar", "#2a9d8f"), (.18, "melengkung", "#e9c46a")]:
            vals = [next((float(r["proporsi"]) for r in rows if r["condition"] == cond and r["cause"] == cause), 0) for cause in use_causes]
            ax.barh(y + offset, vals, .34, label=cond.capitalize() if offset < 0 else "Melengkung", color=color)
        ax.set_yticks(y, labels)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Proporsi")
        ax.set_title("FP" if kind == "FP" else "FN")
        ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(ASSETS / "gambar_4_13_error_causes_by_condition.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    timing_md = """# Ringkasan waktu pasca-evaluasi\n\n"""
    timing_md += "Profil serial matcher lokal hanya mencakup enam sampel teks yang sudah diukur sebelum evaluasi penuh, bukan semua 160 foto. Angka per kondisi di bawah adalah ringkasan sampel gabungan antara teks evaluasi dan kalibrasi; evaluasi 160 sendiri dijalankan paralel dan tidak menyimpan durasi matcher per foto.\n\n"
    timing_md += "| Kondisi | N sampel | Rata-rata matcher | Median | Minimum | Maksimum |\n|---|---:|---:|---:|---:|---:|\n"
    for row in timing_rows:
        timing_md += f"| {row['condition']} | {row['n_sample']} | {row['mean_seconds']:.2f} dtk | {row['median_seconds']:.2f} dtk | {row['min_seconds']:.2f} dtk | {row['max_seconds']:.2f} dtk |\n"
    timing_md += f"\nOCR Colab pada CSV evaluasi: rata-rata {statistics.mean(ocr_times):.2f} detik/foto ({len(ocr_times)} foto). Perangkat tercatat lewat metadata runtime pada CSV.\n\n"
    timing_md += "Ablation menyimpan durasi per foto dan versi EasyOCR/Torch/OpenCV, tetapi tidak menyimpan status CUDA aktual atau nama GPU. Karena itu artefak tersebut tidak membuktikan adanya pengukuran OCR lokal CPU; angka waktu ablation disertakan di CSV terpisah tanpa mengatribusikannya ke CPU. Tidak ada OCR yang dijalankan ulang untuk membuat laporan ini.\n"
    (ROOT / "docs/evaluation/timing_summary.md").write_text(timing_md, encoding="utf-8")

    inputs = [GT_PATH, OCR_PATH, PRED_PATH, DETAIL_PATH, SUMMARY_PATH]
    manifest = {"photos": 160, "bootstrap": {"iterations": 1000, "seed": 42},
                "inputs_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
                "error_cause_method": "deterministic heuristic; source evidence and definitions are documented in post_evaluation_analysis.md",
                "evaluation_rerun": False}
    (OUT / "post_evaluation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packaged = ["verdict_confusion_3x3.csv", "verdict_status_5x3.csv", "verdict_quality_bootstrap.json",
                "error_cause_summary_by_condition.csv", "error_examples_seed42.csv",
                "composition_extraction_summary.csv", "matcher_timing_profile_summary.csv",
                "timing_ocr_metadata.json", "ablation_ocr_timing_by_condition.csv"]
    for filename in packaged:
        shutil.copy2(OUT / filename, ASSETS / filename)
    captions = ASSETS / "captions.md"
    if captions.exists():
        current = captions.read_text(encoding="utf-8-sig").rstrip()
        current += "\n- Gambar 4.12. Matriks konfusi verdict produk pada 160 foto evaluasi.\n"
        current += "- Gambar 4.13. Proporsi kategori penyebab kesalahan bahan menurut kondisi foto.\n"
        captions.write_text(current, encoding="utf-8")
    print(f"Wrote aggregate audit artifacts to {OUT}; examples={len(examples)}; dangerous verdict misses={len(dangerous)}")


if __name__ == "__main__":
    main()
