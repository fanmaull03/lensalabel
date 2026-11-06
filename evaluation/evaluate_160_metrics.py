"""Compute entry, category-presence, product-verdict and OCR-text metrics.

The normal path reads persisted OCR only. ``--transcript-smoke-test`` is an
explicit diagnostic that substitutes human transcript text for OCR and is
never an official prediction run.

For the 3-class product-verdict matrix, system ``perlu_verifikasi`` and
``tidak_terbaca`` map to ``perhatian``. The separate 5-by-3 status table keeps
those raw system statuses visible against the GT's 3-class strongest-category
verdict; its counts are also written separately for each photo condition.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import random
import re
import sys
import unicodedata
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.frozen_config import load_config  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fields or list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = "".join(" " if unicodedata.category(char).startswith("P") else char for char in value)
    return re.sub(r"\s+", " ", value).strip()


def edit_distance(reference: list[str], hypothesis: list[str], *, local: bool) -> int:
    previous = [0 if local else j for j in range(len(hypothesis) + 1)]
    for i, ref_item in enumerate(reference, start=1):
        current = [i] + [0] * len(hypothesis)
        for j, hyp_item in enumerate(hypothesis, start=1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1,
                             previous[j - 1] + (ref_item != hyp_item))
        previous = current
    return min(previous) if local and previous else (previous[-1] if previous else len(reference))


def text_errors(reference: str, hypothesis: str, *, local: bool) -> tuple[float, float]:
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    char_error = edit_distance(list(ref), list(hyp), local=local) / max(1, len(ref))
    word_error = edit_distance(ref.split(), hyp.split(), local=local) / max(1, len(ref.split()))
    return char_error, word_error


def score_counts(gt: set[str], pred: set[str], categories: dict[str, str], category: str | None = None):
    if category:
        gt = {name for name in gt if categories.get(name) == category}
        pred = {name for name in pred if categories.get(name) == category}
    tp, fp, fn = len(gt & pred), len(pred - gt), len(gt - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return tp, fp, fn, precision, recall, f1


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


LABELS = ("aman", "perhatian", "hindari")
SYSTEM_STATUSES = ("aman", "perhatian", "hindari", "perlu_verifikasi", "tidak_terbaca")
PRIORITY = {"aman": 0, "perhatian": 1, "hindari": 2}


def strongest_category(categories: set[str]) -> str:
    return max(categories, key=lambda c: PRIORITY.get(c, -1), default="aman")


def ocr_hypothesis(filename: str, transcripts: dict[str, str], ocr_by_name: dict[str, dict[str, str]], *, transcript_mode: bool) -> str:
    """Select saved OCR text, or explicitly substitute the human transcript for smoke tests."""
    return transcripts[filename] if transcript_mode else ocr_by_name[filename]["ocr_text"]


def metric_triplet(records: list[dict], level: str, category: str | None = None) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for row in records:
        if level == "ingredient":
            gt, pred = set(row["gt_names"]), set(row["pred_names"])
            if category:
                gt = {n for n in gt if row["category_by_name"].get(n) == category}
                pred = {n for n in pred if row["category_by_name"].get(n) == category}
        else:
            gt, pred = set(row["gt_categories"]), set(row["pred_categories"])
            if category:
                gt = {c for c in gt if c == category}
                pred = {c for c in pred if c == category}
        tp += len(gt & pred)
        fp += len(pred - gt)
        fn += len(gt - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, 2 * p * r / (p + r) if p + r else 0.0


def verdict_stats(records: list[dict], category: str | None = None) -> tuple[float, float, float, list[list[int]]]:
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for row in records:
        actual, predicted = row["gt_verdict"], row["pred_verdict"]
        if actual not in LABELS or predicted not in LABELS:
            continue
        matrix[LABELS.index(actual)][LABELS.index(predicted)] += 1
    if category:
        index = LABELS.index(category)
        tp = matrix[index][index]
        fp = sum(matrix[i][index] for i in range(len(LABELS)) if i != index)
        fn = sum(matrix[index][j] for j in range(len(LABELS)) if j != index)
    else:
        tp = sum(matrix[i][i] for i in range(len(LABELS)))
        fp = sum(sum(matrix[i][j] for i in range(len(LABELS))) for j in range(len(LABELS))) - tp
        fn = fp
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, 2 * p * r / (p + r) if p + r else 0.0, matrix


def system_status_cross_tab(records: list[dict], *, scope: str = "keseluruhan") -> list[dict]:
    """Count raw 5-state system outcomes against the GT's 3-class verdict."""
    selected = records if scope == "keseluruhan" else [r for r in records if r["condition"] == scope]
    counts = {(status, gt): 0 for status in SYSTEM_STATUSES for gt in LABELS}
    for row in selected:
        key = (row["system_status"], row["gt_verdict"])
        if key in counts:
            counts[key] += 1
    return [{"cakupan": scope, "status_sistem": status, "verdict_gt": gt,
             "jumlah": counts[(status, gt)]}
            for status in SYSTEM_STATUSES for gt in LABELS]


def bootstrap_summary(records: list[dict], *, iterations: int = 1000, seed: int = 42) -> tuple[list[dict], list[dict]]:
    summary, confusion = [], []
    scopes = [("keseluruhan", records), ("datar", [r for r in records if r["condition"] == "datar"]),
              ("melengkung", [r for r in records if r["condition"] == "melengkung"])]
    for scope, group in scopes:
        if not group:
            continue
        rng = np.random.default_rng(seed)
        resamples = rng.integers(0, len(group), size=(iterations, len(group)))
        for level in ("ingredient", "category"):
            for category in (None, *LABELS):
                counts = []
                for row in group:
                    gt = set(row["gt_names"] if level == "ingredient" else row["_gt_categories"])
                    pred = set(row["pred_names"] if level == "ingredient" else row["_pred_categories"])
                    if category:
                        lookup = row["category_by_name"] if level == "ingredient" else {c: c for c in row["_gt_categories"] | row["_pred_categories"]}
                        gt = {x for x in gt if lookup.get(x) == category}
                        pred = {x for x in pred if lookup.get(x) == category}
                    counts.append((len(gt & pred), len(pred - gt), len(gt - pred)))
                arr = np.asarray(counts, dtype=np.int64)
                sampled = arr[resamples].sum(axis=1)
                def prf(count_array):
                    tp, fp, fn = count_array.T
                    p = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) != 0)
                    r = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) != 0)
                    f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) != 0)
                    return p, r, f1
                point = prf(arr.sum(axis=0, keepdims=True))
                samples = prf(sampled)
                for metric, value, vals in zip(("precision", "recall", "f1"), [float(x[0]) for x in point], samples):
                    summary.append({"level": level, "cakupan": scope, "kategori": category or "semua",
                                    "metrik": metric, "nilai": value,
                                    "ci95_bawah": float(np.quantile(vals, .025)), "ci95_atas": float(np.quantile(vals, .975)),
                                    "resampling": iterations, "seed": seed, "jumlah_foto": len(group)})
        photo_matrices = np.zeros((len(group), 3, 3), dtype=np.int64)
        for i, row in enumerate(group):
            if row["gt_verdict"] in LABELS and row["pred_verdict"] in LABELS:
                photo_matrices[i, LABELS.index(row["gt_verdict"]), LABELS.index(row["pred_verdict"])] = 1
        matrices = photo_matrices.sum(axis=0)
        sampled_matrices = photo_matrices[resamples].sum(axis=1)
        for category in (None, *LABELS):
            if category:
                idx = LABELS.index(category)
                tp = matrices[idx, idx]
                fp = matrices[:, idx].sum() - tp
                fn = matrices[idx, :].sum() - tp
                s_tp = sampled_matrices[:, idx, idx]
                s_fp = sampled_matrices[:, :, idx].sum(axis=1) - s_tp
                s_fn = sampled_matrices[:, idx, :].sum(axis=1) - s_tp
            else:
                tp = np.trace(matrices)
                fp = matrices.sum() - tp
                fn = fp
                s_tp = np.trace(sampled_matrices, axis1=1, axis2=2)
                s_fp = sampled_matrices.sum(axis=(1, 2)) - s_tp
                s_fn = s_fp
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * p * r / (p + r) if p + r else 0.0
            sp, sr, sf = prf(np.stack((s_tp, s_fp, s_fn), axis=1))
            samples = (sp, sr, sf)
            for metric, value, vals in zip(("precision", "recall", "f1"), (p, r, f1), samples):
                summary.append({"level": "verdict_produk", "cakupan": scope, "kategori": category or "akurasi_micro",
                                "metrik": metric, "nilai": value,
                                "ci95_bawah": float(np.quantile(vals, .025)), "ci95_atas": float(np.quantile(vals, .975)),
                                "resampling": iterations, "seed": seed, "jumlah_foto": len(group)})
            if category is None:
                for actual_i, actual in enumerate(LABELS):
                    denom = int(matrices[actual_i].sum())
                    for pred_i, predicted in enumerate(LABELS):
                        row_denoms = sampled_matrices[:, actual_i, :].sum(axis=1)
                        cell_samples = np.divide(sampled_matrices[:, actual_i, pred_i], row_denoms,
                                                 out=np.zeros(iterations, dtype=float), where=row_denoms != 0)
                        confusion.append({"cakupan": scope, "verdict_gt": actual, "verdict_prediksi": predicted,
                                          "jumlah": matrices[actual_i][pred_i], "proporsi_baris": matrices[actual_i][pred_i] / denom if denom else 0.0,
                                          "ci95_bawah": float(np.quantile(cell_samples, .025)), "ci95_atas": float(np.quantile(cell_samples, .975)),
                                          "resampling": iterations, "seed": seed})
    return summary, confusion


def synthetic_self_test() -> None:
    rows = [
        {"condition": "datar", "gt_names": {"A"}, "pred_names": {"A"},
         "gt_categories": {"hindari"}, "pred_categories": {"hindari"},
         "_gt_categories": {"hindari"}, "_pred_categories": {"hindari"}, "category_by_name": {"A": "hindari"},
         "gt_verdict": "hindari", "pred_verdict": "hindari"},
        {"condition": "melengkung", "gt_names": {"B"}, "pred_names": {"A"},
         "gt_categories": {"aman"}, "pred_categories": {"hindari"},
         "_gt_categories": {"aman"}, "_pred_categories": {"hindari"}, "category_by_name": {"A": "hindari", "B": "aman"},
         "gt_verdict": "aman", "pred_verdict": "hindari", "system_status": "perlu_verifikasi"},
    ]
    rows[0]["system_status"] = "hindari"
    assert metric_triplet(rows, "ingredient") == (0.5, 0.5, 0.5)
    assert metric_triplet(rows, "category", "hindari") == (0.5, 1.0, 2 / 3)
    _, _, _, matrix = verdict_stats(rows)
    assert matrix[LABELS.index("hindari")][LABELS.index("hindari")] == 1
    cross_tab = system_status_cross_tab(rows)
    assert len(cross_tab) == 15
    assert next(r for r in cross_tab if r["status_sistem"] == "perlu_verifikasi" and r["verdict_gt"] == "aman")["jumlah"] == 1
    assert next(r for r in cross_tab if r["status_sistem"] == "hindari" and r["verdict_gt"] == "hindari")["jumlah"] == 1
    summary, cm = bootstrap_summary(rows, iterations=25, seed=42)
    assert summary and cm and all(r["ci95_bawah"] <= r["nilai"] <= r["ci95_atas"] or r["nilai"] in (0, 1) for r in summary)
    print("Synthetic metric self-test lulus.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-imports", action="store_true",
                        help="Validasi impor dan sumber data tanpa menghitung metrik.")
    parser.add_argument("--transcript-smoke-test", action="store_true",
                        help="Gunakan transcripts.csv sebagai teks OCR pengganti; bukan prediksi OCR foto.")
    parser.add_argument("--smoke-limit", type=int, default=6,
                        help="Jumlah awal foto split untuk smoke test berbasis transkrip (default 6).")
    parser.add_argument("--self-test", action="store_true", help="Uji metrik sintetis tanpa membaca dataset.")
    args = parser.parse_args()
    if args.self_test:
        synthetic_self_test()
        return
    config = load_config(require_frozen=not (args.check_imports or args.transcript_smoke_test))
    output_dir = ROOT / "evaluation" / "results" / "evaluation_ocr"
    gt_path = ROOT / str(config.get("evaluation_gt_path", "evaluation/ground_truth/evaluation_gt_final.json"))
    if not gt_path.is_file():
        raise FileNotFoundError(f"evaluation_gt_final.json belum ada: {gt_path}")
    expected_gt_hash = config.get("evaluation_gt_sha256")
    if not expected_gt_hash:
        raise RuntimeError("Config frozen harus mencatat evaluation_gt_sha256 sebelum metrik dihitung.")
    actual_gt_hash = sha256(gt_path)
    if actual_gt_hash.casefold() != str(expected_gt_hash).casefold():
        raise RuntimeError("Hash evaluation GT berbeda dari config_frozen.json; metrik ditolak.")

    ocr_path = output_dir / "evaluation_ocr_160.csv"
    if not (args.check_imports or args.transcript_smoke_test) and not ocr_path.is_file():
        raise FileNotFoundError(f"Hasil OCR 160 foto belum ada: {ocr_path}")
    split_rows = read_csv(ROOT / "evaluation" / "splits" / "evaluation_set.csv")
    if len(split_rows) != 160 or len({r["filename"] for r in split_rows}) != 160:
        raise RuntimeError("Manifest evaluasi harus memiliki 160 foto unik.")
    split = {row["filename"]: row["category"] for row in split_rows}
    ocr_rows = read_csv(ocr_path) if ocr_path.is_file() and not args.transcript_smoke_test else []
    ocr_by_name = {row["filename"]: row for row in ocr_rows}
    if not (args.check_imports or args.transcript_smoke_test) and set(ocr_by_name) != set(split):
        raise RuntimeError("OCR CSV harus mencakup tepat seluruh 160 foto evaluasi.")

    gt_doc = json.loads(gt_path.read_text(encoding="utf-8-sig"))
    if set(gt_doc) != set(split):
        raise RuntimeError("evaluation_gt_final.json harus mencakup tepat seluruh 160 foto.")
    transcript_rows = read_csv(ROOT / "dataset" / "ground_truth" / "transcripts.csv")
    transcripts = {row["filename"]: row["ground_truth_text"] for row in transcript_rows}
    if not set(split).issubset(transcripts):
        raise RuntimeError("Transkrip teks belum lengkap untuk foto evaluasi.")

    kb_path = ROOT / str(config["kb_path"])
    kb_doc = json.loads(kb_path.read_text(encoding="utf-8-sig"))
    if sha256(kb_path).casefold() != str(config["kb_sha256"]).casefold():
        raise RuntimeError("Hash KB berbeda dari config_frozen.json; metrik ditolak.")
    flat_kb = []
    category_by_name = {}
    used_ids: set[int] = set()
    next_id = max((int(old) for entry in kb_doc["ingredients"] for old in entry.get("old_entry_ids", [])), default=0) + 1
    for entry in kb_doc["ingredients"]:
        ingredient_id = next((int(old) for old in entry.get("old_entry_ids", []) if int(old) not in used_ids), None)
        if ingredient_id is None:
            while next_id in used_ids:
                next_id += 1
            ingredient_id, next_id = next_id, next_id + 1
        used_ids.add(ingredient_id)
        name = str(entry["standard_name"])
        category_by_name[name] = str(entry["category"]).casefold()
        for variant in [name, *entry.get("synonyms", [])]:
            flat_kb.append({"ingredient_id": ingredient_id, "standard_name": name,
                            "category": entry["category"], "name_variant": str(variant)})

    sys.path.insert(0, str(ROOT / "backend"))
    from app.classifier.rule_based import classify_product  # noqa: E402
    from app.matching.fuzzy_matcher import match_token_many  # noqa: E402
    from app.matching.pair_blocks import pair_data  # noqa: E402
    from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402

    runtime_blocked_pairs = pair_data()["active_pairs"] + pair_data().get("expert_distinct_pairs", [])
    if config["blocked_pairs"] != runtime_blocked_pairs:
        raise RuntimeError("Daftar blocked_pairs di config berbeda dari sumber runtime chemical_pair_blocks.json.")

    if args.check_imports:
        print("Import check selesai; tidak ada OCR atau evaluasi yang dijalankan.")
        return

    threshold = float(config["threshold"])
    weights = {key: float(value) for key, value in config["weights"].items()}
    length_penalty_exponent = float(config["length_penalty"]["exponent"])
    photo_rows = []
    ingredient_categories = {name: str(row.get("category", category_by_name.get(name, ""))).casefold()
                             for doc in gt_doc.values() for row in doc.get("ingredients", [])
                             for name in [str(row["standard_name"])]}
    category_by_name.update(ingredient_categories)

    selected_split = list(split.items())
    if args.transcript_smoke_test:
        if args.smoke_limit < 1:
            raise ValueError("--smoke-limit harus positif.")
        per_condition = max(1, args.smoke_limit // 2)
        selected_split = []
        for condition in ("datar", "melengkung"):
            selected_split.extend([(name, cond) for name, cond in split.items() if cond == condition][:per_condition])
    for filename, condition in selected_split:
        ocr_text = ocr_hypothesis(filename, transcripts, ocr_by_name, transcript_mode=args.transcript_smoke_test)
        composition = extract_composition_section(ocr_text)
        tokens = tokenize(composition)
        matches = [m for token in tokens for m in match_token_many(
            token, flat_kb, weights=weights, threshold=threshold, shared_heads=True,
            length_penalty_exponent=length_penalty_exponent,
        )]
        classified = classify_product(matches)
        pred = {item["standard_name"] for key in ("aman", "perhatian", "hindari")
                for item in classified[key]}
        expected_items = gt_doc[filename].get("ingredients", [])
        gt_names = {str(item["standard_name"]) for item in expected_items}
        gt_categories = {str(item["standard_name"]): str(item.get("category", "")).casefold()
                         for item in expected_items}
        category_map = {**category_by_name, **gt_categories}
        counts = score_counts(gt_names, pred, category_map)
        gt_categories_set = {gt_categories.get(name, category_map.get(name, "aman")) for name in gt_names}
        pred_categories_set = {category_map.get(name, "aman") for name in pred}
        gt_verdict = strongest_category(gt_categories_set)
        # The production classifier's uncertainty states map to Perhatian in
        # the requested three-class matrix; the mapping is recorded in output.
        system_status = classified["verdict"]
        pred_verdict = system_status
        if pred_verdict in {"perlu_verifikasi", "tidak_terbaca"}:
            pred_verdict = "perhatian"
        per_photo = {"filename": filename, "condition": condition,
                     "ground_truth": sorted(gt_names), "predicted": sorted(pred),
                     "gt_names": gt_names, "pred_names": pred,
                     "_gt_categories": gt_categories_set, "_pred_categories": pred_categories_set,
                     "gt_categories": sorted(gt_categories_set), "predicted_categories": sorted(pred_categories_set),
                     "gt_verdict": gt_verdict, "pred_verdict": pred_verdict, "system_status": system_status,
                     "category_by_name": category_map,
                     "tp": counts[0], "fp": counts[1], "fn": counts[2],
                     "precision": counts[3], "recall": counts[4], "f1": counts[5],
                     "ocr_runtime_seconds": 0.0 if args.transcript_smoke_test else float(ocr_by_name[filename]["ocr_runtime_seconds"])}
        for category in ("aman", "perhatian", "hindari"):
            c = score_counts(gt_names, pred, category_map, category)
            per_photo[f"{category}_tp"], per_photo[f"{category}_fp"], per_photo[f"{category}_fn"] = c[:3]
        for version, target, local in (("teks_penuh", ocr_text, False),
                                       ("komposisi", composition, False),
                                       ("lokal", ocr_text, True)):
            cer, wer = text_errors(transcripts[filename], target, local=local)
            per_photo[f"cer_{version}"] = cer
            per_photo[f"wer_{version}"] = wer
        photo_rows.append(per_photo)

    summary_rows, confusion_rows = bootstrap_summary(photo_rows)
    # Add OCR text metrics to the same summary table; bootstrap CIs for these
    # per-photo averages use the identical photo-level resampling design.
    for scope, condition_filter in (("Keseluruhan", None), ("Datar", "datar"), ("Melengkung", "melengkung")):
        items = [row for row in photo_rows if condition_filter is None or row["condition"] == condition_filter]
        for metric in ("cer", "wer"):
            for version in ("teks_penuh", "komposisi", "lokal"):
                values = [float(row[f"{metric}_{version}"]) for row in items]
                rng = random.Random(42)
                boot = [sum(values[rng.randrange(len(values))] for _ in values) / len(values) for _ in range(1000)] if values else [0.0]
                summary_rows.append({"level": metric.upper(), "cakupan": scope, "kategori": version,
                                     "metrik": "mean", "nilai": sum(values) / len(values) if values else 0.0,
                                     "ci95_bawah": percentile(boot, .025), "ci95_atas": percentile(boot, .975),
                                     "resampling": 1000, "seed": 42, "jumlah_foto": len(values)})
    ci_rows = [{k: v for k, v in row.items() if k in {"level", "cakupan", "kategori", "metrik", "nilai", "ci95_bawah", "ci95_atas", "resampling", "seed", "jumlah_foto"}} for row in summary_rows]
    output_dir = ROOT / "evaluation" / "results" / ("metrics_transcript_smoke" if args.transcript_smoke_test else "evaluation_ocr")
    detail_rows = [{**r,
                    "gt_names": json.dumps(sorted(r["gt_names"]), ensure_ascii=False),
                    "pred_names": json.dumps(sorted(r["pred_names"]), ensure_ascii=False),
                    "_gt_categories": json.dumps(sorted(r["_gt_categories"]), ensure_ascii=False),
                    "_pred_categories": json.dumps(sorted(r["_pred_categories"]), ensure_ascii=False),
                    "category_by_name": json.dumps(r["category_by_name"], ensure_ascii=False)} for r in photo_rows]
    write_csv(output_dir / "evaluation_metrics_detail.csv", detail_rows)
    write_csv(output_dir / "evaluation_metrics_summary.csv", summary_rows)
    write_csv(output_dir / "evaluation_metrics_bootstrap_ci.csv", ci_rows)
    write_csv(output_dir / "evaluation_verdict_confusion.csv", confusion_rows)
    cross_tab_rows = []
    for scope in ("keseluruhan", "datar", "melengkung"):
        cross_tab_rows.extend(system_status_cross_tab(photo_rows, scope=scope))
    write_csv(output_dir / "evaluation_verdict_status_cross_tab.csv", cross_tab_rows)
    status_counts = [{"status_sistem": status,
                      "jumlah": sum(row["system_status"] == status for row in photo_rows)}
                     for status in SYSTEM_STATUSES]
    write_csv(output_dir / "evaluation_system_status_counts.csv", status_counts)
    method = {
        "ingredient_level": "set of standard_name entries per photo",
        "category_level": "set of KB categories per photo; ingredient names ignored",
        "product_verdict_ground_truth": "highest-risk category among GT ingredients (Hindari > Perhatian > Aman)",
        "product_verdict_system": "classifier verdict; perlu_verifikasi and tidak_terbaca map to Perhatian for the 3-class matrix",
        "verdict_confusion_matrix": "rows=GT verdict, columns=system verdict; 3 classes",
        "system_status_cross_tab": "rows=raw 5-state system status (Aman, Perhatian, Hindari, perlu_verifikasi, tidak_terbaca); columns=GT 3-class strongest-category verdict; counts also per condition",
        "system_status_counts": "jumlah produk dengan masing-masing status sistem mentah; perlu_verifikasi dan tidak_terbaca dilaporkan terpisah",
        "bootstrap": {"unit": "photo", "iterations": 1000, "seed": 42, "confidence": 0.95},
        "mode": "transcript_as_ocr_smoke_test" if args.transcript_smoke_test else "persisted_ocr",
    }
    (output_dir / "evaluation_metrics_method.json").write_text(json.dumps(method, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Metrics tersimpan di {output_dir}; threshold={threshold:g}; foto_dihitung={len(photo_rows)}; bootstrap=1000 seed=42.")
    print("MODE: transcript-as-OCR smoke test; bukan evaluasi OCR/foto." if args.transcript_smoke_test else "MODE: hasil OCR tersimpan.")


if __name__ == "__main__":
    main()
