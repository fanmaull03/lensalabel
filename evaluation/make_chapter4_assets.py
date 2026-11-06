"""Build repeatable Chapter IV tables and figures from persisted evaluation outputs.

The default run is a calibration-only dry run. It reads the saved calibration
grid and OCR cache, the two split manifests (metadata only), and expert review
rows. It never runs OCR or the matcher. Evaluation results are accepted only
when their provenance matches the supplied GT and KB hashes for a final run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import statistics
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.frozen_config import load_config  # noqa: E402

DEFAULT_RESULTS = ROOT / "evaluation" / "results" / "colab_v4"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results" / "chapter4"
CAL_SPLIT = ROOT / "evaluation" / "splits" / "calibration_set.csv"
EVAL_SPLIT = ROOT / "evaluation" / "splits" / "evaluation_set.csv"
CAL_GT = ROOT / "dataset" / "ground_truth" / "calibration_ingredients_gt_final.json"
EXPERT_REVIEW = ROOT / "evaluation" / "results" / "kb_v2_phase2" / "kb_v2_review.json"
RAW_PHOTOS = ROOT / "dataset" / "raw_photos"
CATEGORIES = ("aman", "perhatian", "hindari")
CATEGORY_LABEL = {"aman": "Aman", "perhatian": "Perlu Perhatian", "hindari": "Hindari"}


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_list(value: str) -> list[str]:
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def write_table(output: Path, stem: str, rows: list[dict[str, Any]], dryrun: bool) -> None:
    prefix = "dryrun_" if dryrun else ""
    csv_path = output / f"{prefix}{stem}.csv"
    xlsx_path = output / f"{prefix}{stem}.xlsx"
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ["status"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = stem[:31]
    ws.append(fields)
    for row in rows:
        ws.append([row.get(k, "") for k in fields])
    style_sheet(ws)
    wb.save(xlsx_path)


def style_sheet(ws: Any) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="264653")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column in ws.columns:
        letter = column[0].column_letter
        max_len = min(max((len(str(c.value or "")) for c in column), default=10), 52)
        ws.column_dimensions[letter].width = max(12, max_len + 2)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def add_workbook(output: Path, tables: dict[str, list[dict[str, Any]]], dryrun: bool) -> None:
    prefix = "dryrun_" if dryrun else ""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in tables.items():
        ws = wb.create_sheet(name[:31])
        fields = list(dict.fromkeys(k for row in rows for k in row)) or ["status"]
        ws.append(fields)
        for row in rows:
            ws.append([row.get(k, "") for k in fields])
        style_sheet(ws)
    wb.save(output / f"{prefix}tabel_bab_iv.xlsx")


def normalize_category(value: str) -> str:
    val = (value or "").strip().lower()
    return {"hindari": "hindari", "perhatian": "perhatian", "aman": "aman"}.get(val, "tidak_diketahui")


def count_metrics(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def read_kb_categories(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    data = read_json(path)
    by_name: dict[str, str] = {}
    variants: dict[str, list[str]] = defaultdict(list)
    if isinstance(data, list):
        for row in data:
            name = str(row.get("standard_name", ""))
            cat = normalize_category(str(row.get("category", "")))
            if name:
                by_name[name] = cat
                variants[name].append(str(row.get("name_variant", name)))
    elif isinstance(data, dict):
        for entry in data.get("ingredients", []):
            name = str(entry.get("standard_name", ""))
            cat = normalize_category(str(entry.get("category", "")))
            if name:
                by_name[name] = cat
                variants[name].extend([name, *map(str, entry.get("synonyms", []))])
    return by_name, variants


def normalize_text(value: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in value).split())


def composition_text(raw: str) -> str:
    """Use saved OCR text as-is; provide a readable text block for panels."""
    return raw.strip()


def load_cache_text(cache_dir: Path, filename: str) -> str:
    path = cache_dir / f"{filename}.json"
    if not path.exists():
        return "[Teks OCR tersimpan tidak tersedia]"
    cache = read_json(path)
    # Reading order here is deliberately simple: detections are already retained
    # from the saved OCR run; this generator does not call OCR or the matcher.
    detections = cache.get("detections", [])
    return "\n".join(str(d.get("text", "")) for d in detections if d.get("text"))


def make_error_rows(detail: list[dict[str, str]], cache_dir: Path, variants: dict[str, list[str]], threshold: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = [r for r in detail if int(float(r["threshold"])) == threshold]
    fp_rows: list[dict[str, Any]] = []
    fn_rows: list[dict[str, Any]] = []
    for row in selected:
        filename = row["filename"]
        ocr = load_cache_text(cache_dir, filename)
        norm_ocr = normalize_text(ocr)
        for name in parse_list(row.get("false_positive", "[]")):
            variant_found = next((v for v in variants.get(name, [name]) if normalize_text(v) and normalize_text(v) in norm_ocr), "")
            cause = "Ada varian literal di OCR; tinjau konteks atau kecocokan fuzzy" if variant_found else "Tidak ada varian literal yang jelas di OCR; kemungkinan noise atau alias terlalu umum"
            fp_rows.append({"foto": filename, "teks_ocr": ocr, "bahan": name, "dugaan_penyebab": cause})
        for name in parse_list(row.get("false_negative", "[]")):
            variants_here = variants.get(name, [name])
            found = next((v for v in variants_here if normalize_text(v) and normalize_text(v) in norm_ocr), "")
            cause = "Varian KB ditemukan literal di OCR; kemungkinan skor atau segmentasi matcher" if found else "Varian KB tidak ditemukan literal; kemungkinan OCR atau kesenjangan varian"
            fn_rows.append({"foto": filename, "teks_ocr": ocr, "bahan": name, "dugaan_penyebab": cause})
    fp_counts = Counter(row["bahan"] for row in fp_rows)
    fn_counts = Counter(row["bahan"] for row in fn_rows)
    for row in fp_rows:
        row["frekuensi_bahan"] = fp_counts[row["bahan"]]
    for row in fn_rows:
        row["frekuensi_bahan"] = fn_counts[row["bahan"]]
    fp_rows.sort(key=lambda x: (-x["frekuensi_bahan"], x["bahan"], x["foto"]))
    fn_rows.sort(key=lambda x: (-x["frekuensi_bahan"], x["bahan"], x["foto"]))
    return fp_rows[:10], fn_rows[:10]


def output_figure(path: Path, fig: Any) -> None:
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_placeholder_chart(path: Path, message: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=17, wrap=True)
    ax.set_axis_off()
    output_figure(path, fig)


def build_assets(args: argparse.Namespace) -> None:
    dryrun = args.mode == "dryrun"
    frozen_config = load_config(require_frozen=not dryrun)
    configured_threshold = int(frozen_config["threshold"])
    if args.error_threshold is not None and args.error_threshold != configured_threshold:
        raise ValueError("--error-threshold harus sama dengan threshold di config_frozen.json")
    args.error_threshold = configured_threshold
    args.ground_truth = args.ground_truth or ROOT / frozen_config["calibration_gt_path"]
    args.kb_snapshot = args.kb_snapshot or ROOT / frozen_config["kb_path"]
    if sha256(args.ground_truth) != frozen_config.get("calibration_gt_sha256"):
        raise ValueError("Hash calibration GT tidak cocok dengan config_frozen.json")
    if sha256(args.kb_snapshot) != frozen_config.get("kb_sha256"):
        raise ValueError("Hash KB tidak cocok dengan config_frozen.json")
    out: Path = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    prefix = "dryrun_" if dryrun else ""
    # Dry run is strictly calibration-only: it does not read the evaluation
    # split, photos, OCR output, GT or predictions.
    cal_rows = read_csv(args.calibration_split)
    allowed_cal = {r["filename"] for r in cal_rows}
    split_counts = Counter(("Kalibrasi", r["category"]) for r in cal_rows)
    split_table = [
        {"split": split, "kondisi": condition, "jumlah_foto": n,
         "catatan": "Dry run hanya membaca split kalibrasi"}
        for (split, condition), n in sorted(split_counts.items())
    ]

    summary_path = args.results_dir / "grid_summary.csv"
    detail_path = args.results_dir / "grid_detail.csv"
    if not summary_path.exists() or not detail_path.exists():
        raise FileNotFoundError("grid_summary.csv dan grid_detail.csv diperlukan")
    summaries = read_csv(summary_path)
    detail_all = read_csv(detail_path)
    detail = [r for r in detail_all if r.get("filename") in allowed_cal]
    other_names = sorted({r.get("filename", "") for r in detail_all} - allowed_cal)
    if other_names and dryrun:
        raise ValueError("Dry run mendeteksi baris non-kalibrasi pada grid_detail; hentikan untuk menjaga batas 40 foto")
    if len({r["filename"] for r in detail}) > 40:
        raise ValueError("Dry run hanya boleh memproses maksimal 40 foto kalibrasi")

    gt_hash = sha256(args.ground_truth)
    kb_hash = sha256(args.kb_snapshot)
    run_manifest_path = args.results_dir / "runtime.json"
    run_manifest = read_json(run_manifest_path) if run_manifest_path.exists() else {}
    signature_path = args.results_dir / "input_signature.txt"
    signature_text = signature_path.read_text(encoding="utf-8-sig") if signature_path.exists() else ""
    declared_gt_hash = None
    declared_kb_hash = None
    best_path = args.results_dir / "best_threshold.json"
    best_blob = read_json(best_path) if best_path.exists() else {}
    best_blob = best_blob.get("best", {})
    try:
        matcher_source = (ROOT / "backend" / "app" / "matching" / "fuzzy_matcher.py").read_text(encoding="utf-8")
        length_penalty = 0.8 if "length_ratio**0.8" in matcher_source else None
    except OSError:
        length_penalty = None
    # The best-threshold file declares the KB and GT hashes from that run.
    best_full = read_json(best_path) if best_path.exists() else {}
    declared_kb_hash = best_full.get("kb_sha256")
    declared_gt_hash = best_full.get("final_gt_sha256")
    stale = bool((declared_kb_hash and declared_kb_hash != kb_hash) or (declared_gt_hash and declared_gt_hash != gt_hash))
    if args.mode == "final" and stale:
        raise ValueError("Provenance hasil grid tidak cocok dengan hash GT/KB saat ini; finalisasi ditolak")

    kb_categories, variants = read_kb_categories(args.kb_snapshot)
    metrics_rows: list[dict[str, Any]] = []
    # CER/WER require a persisted OCR metric file selected explicitly. The dry
    # run does not recalculate OCR metrics from images or transcripts.
    ocr_rows: list[dict[str, str]] = []
    if args.ocr_metrics:
        ocr_rows = [r for r in read_csv(args.ocr_metrics) if r.get("filename") in allowed_cal]
    for metric in ("CER", "WER"):
        if ocr_rows:
            key = metric.lower()
            groups = [("Keseluruhan", ocr_rows), ("Datar", [r for r in ocr_rows if r.get("category") == "datar"]), ("Melengkung", [r for r in ocr_rows if r.get("category") == "melengkung"])]
            for scope, items in groups:
                vals = [float(r[key]) for r in items if r.get(key) not in (None, "")]
                metrics_rows.append({"metrik": metric, "cakupan": scope, "kategori": "Semua", "threshold": "", "nilai": statistics.mean(vals) if vals else "", "jumlah_foto": len(vals), "status_data": "tersedia" if vals else "tidak tersedia"})
        else:
            for scope in ("Keseluruhan", "Datar", "Melengkung"):
                metrics_rows.append({"metrik": metric, "cakupan": scope, "kategori": "Semua", "threshold": "", "nilai": "", "jumlah_foto": 0, "status_data": "belum ada file metrik OCR tersimpan"})

    # Entry, category-presence, and product-verdict summaries by condition.
    # The dry-run source remains the saved calibration grid only.
    for threshold in sorted({int(float(r["threshold"])) for r in detail}):
        rows_t = [r for r in detail if int(float(r["threshold"])) == threshold]
        scopes: list[tuple[str, list[dict[str, str]]]] = [("Keseluruhan", rows_t), ("Datar", [r for r in rows_t if r.get("category", r.get("condition")) == "datar"]), ("Melengkung", [r for r in rows_t if r.get("category", r.get("condition")) == "melengkung"])]
        for scope, items in scopes:
            for level in ("bahan", "kategori"):
              for category in (*CATEGORIES, "tidak_diketahui"):
                tp = fp = fn = 0
                for row in items:
                    gt = set(parse_list(row.get("ground_truth", "[]")))
                    pred = set(parse_list(row.get("predicted", "[]")))
                    if level == "bahan":
                        gt_units, pred_units = gt, pred
                        item_category = lambda name: kb_categories.get(name, "tidak_diketahui")
                    else:
                        gt_units = {kb_categories.get(n, "tidak_diketahui") for n in gt}
                        pred_units = {kb_categories.get(n, "tidak_diketahui") for n in pred}
                        item_category = lambda value: value
                    gt_units = {x for x in gt_units if item_category(x) == category}
                    pred_units = {x for x in pred_units if item_category(x) == category}
                    tp += len(gt_units & pred_units)
                    fp += len(pred_units - gt_units)
                    fn += len(gt_units - pred_units)
                p, r, f1 = count_metrics(tp, fp, fn)
                metrics_rows.extend([
                    {"level": level, "metrik": "Precision", "cakupan": scope, "kategori": CATEGORY_LABEL.get(category, "Tidak diketahui"), "threshold": threshold, "nilai": p, "jumlah_foto": len(items), "status_data": "tersedia"},
                    {"level": level, "metrik": "Recall", "cakupan": scope, "kategori": CATEGORY_LABEL.get(category, "Tidak diketahui"), "threshold": threshold, "nilai": r, "jumlah_foto": len(items), "status_data": "tersedia"},
                    {"level": level, "metrik": "F1", "cakupan": scope, "kategori": CATEGORY_LABEL.get(category, "Tidak diketahui"), "threshold": threshold, "nilai": f1, "jumlah_foto": len(items), "status_data": "tersedia"},
                ])
            # Product-level verdict: GT is the highest-risk ingredient class;
            # the saved classifier verdict is already present per grid row.
            verdict_matrix = Counter()
            for row in items:
                gt_names = set(parse_list(row.get("ground_truth", "[]")))
                gt_levels = [kb_categories.get(name, "tidak_diketahui") for name in gt_names]
                gt_verdict = max(gt_levels, key=lambda v: {"aman": 0, "perhatian": 1, "hindari": 2}.get(v, -1), default="aman")
                pred_verdict = str(row.get("verdict", "" )).casefold()
                if pred_verdict in {"tidak_terbaca", "perlu_verifikasi"}:
                    pred_verdict = "perhatian"
                if gt_verdict in CATEGORIES and pred_verdict in CATEGORIES:
                    verdict_matrix[(gt_verdict, pred_verdict)] += 1
            for actual in CATEGORIES:
                tp = verdict_matrix[(actual, actual)]
                fp = sum(verdict_matrix[(other, actual)] for other in CATEGORIES if other != actual)
                fn = sum(verdict_matrix[(actual, other)] for other in CATEGORIES if other != actual)
                p, r, f1 = count_metrics(tp, fp, fn)
                metrics_rows.extend([{"level": "verdict_produk", "metrik": met, "cakupan": scope,
                                      "kategori": CATEGORY_LABEL[actual], "threshold": threshold,
                                      "nilai": value, "jumlah_foto": len(items), "status_data": "tersedia"}
                                     for met, value in (("Precision", p), ("Recall", r), ("F1", f1))])
    # Keep the run's overall P/R/F1 as saved values, documenting that this is
    # the producer's aggregate calculation.
    for s in summaries:
        if s.get("cakupan") != "Keseluruhan" or s.get("kategori") != "semua":
            continue
        for metric in ("precision", "recall", "f1"):
            metrics_rows.append({"metrik": metric.upper(), "cakupan": "Keseluruhan (hasil tersimpan)", "kategori": "Semua", "threshold": int(s["threshold"]), "nilai": float(s[metric]), "jumlah_foto": int(s.get("n_photos", s.get("foto", 0))), "status_data": "tersedia"})

    # Expert-review summary from the persisted validation rows.
    expert_data = read_json(args.expert_review) if args.expert_review.exists() else {}
    expert_rows = expert_data.get("expert_validation_rows", [])
    approvals = sum(1 for r in expert_rows if str(r.get("expert_correction", "")).strip().lower() in ("setuju", "approved", "disetujui"))
    corrected = sum(1 for r in expert_rows if str(r.get("expert_correction", "")).strip().lower() not in ("setuju", "approved", "disetujui", "", "none"))
    before = Counter(normalize_category(str(r.get("category_initial", ""))) for r in expert_rows)
    after = Counter(normalize_category(str(r.get("category_expert", ""))) for r in expert_rows)
    note_count = sum(1 for r in expert_rows if str(r.get("clinical_note", "")).strip())
    expert_table = [
        {"indikator": "Baris validasi", "nilai": len(expert_rows)},
        {"indikator": "Disetujui", "nilai": approvals},
        {"indikator": "Dikoreksi", "nilai": corrected},
        {"indikator": "Memiliki catatan", "nilai": note_count},
        *[{"indikator": f"Kategori sebelum: {CATEGORY_LABEL.get(c, c)}", "nilai": before.get(c, 0)} for c in CATEGORIES],
        *[{"indikator": f"Kategori sesudah: {CATEGORY_LABEL.get(c, c)}", "nilai": after.get(c, 0)} for c in CATEGORIES],
    ]

    # Error tables: top ten rows, with OCR text from the saved calibration cache.
    cache_dir = args.results_dir / "ocr_cache"
    fp_top, fn_top = make_error_rows(detail, cache_dir, variants, args.error_threshold)
    if not fp_top:
        fp_top = [{"status": "Tidak ada data FP pada threshold yang dipilih"}]
    if not fn_top:
        fn_top = [{"status": "Tidak ada data FN pada threshold yang dipilih"}]

    # Ingredient-level category confusion. A missing side has its own state.
    confusion_labels = ["Aman", "Perlu Perhatian", "Hindari", "Tidak terdeteksi", "Prediksi tambahan"]
    matrix = Counter()
    for row in detail:
        if int(float(row["threshold"])) != args.error_threshold:
            continue
        gt = set(parse_list(row.get("ground_truth", "[]")))
        pred = set(parse_list(row.get("predicted", "[]")))
        for name in gt | pred:
            if name in gt and name in pred:
                a = CATEGORY_LABEL.get(kb_categories.get(name, ""), "Tidak diketahui")
                p = a
            elif name in gt:
                a = CATEGORY_LABEL.get(kb_categories.get(name, ""), "Tidak diketahui")
                p = "Tidak terdeteksi"
            else:
                a = "Prediksi tambahan"
                p = CATEGORY_LABEL.get(kb_categories.get(name, ""), "Tidak diketahui")
            if a in confusion_labels and p in confusion_labels:
                matrix[(a, p)] += 1
    confusion_table = [{"kategori_gt": a, "kategori_prediksi": p, "jumlah_bahan": matrix[(a, p)]} for a in confusion_labels for p in confusion_labels]

    # F1 by threshold chart (saved calibration grid only).
    f1_summary = [(int(s["threshold"]), float(s["f1"])) for s in summaries]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    if f1_summary:
        xs, ys = zip(*sorted(f1_summary))
        ax.plot(xs, ys, marker="o", linewidth=2.5, markersize=7, color="#1f6e8c")
        ax.set_xticks(xs)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Threshold")
        ax.set_ylabel("F1")
        ax.grid(axis="y", alpha=.25)
        ax.tick_params(labelsize=12)
    else:
        ax.text(.5, .5, "Data F1 belum tersedia", ha="center", va="center", fontsize=16)
        ax.set_axis_off()
    output_figure(out / f"{prefix}gambar_4_01_f1_threshold.png", fig)

    # CER/WER by condition chart. Missing source values are represented as an
    # explicit placeholder rather than synthesized from OCR or transcript text.
    cerwer = [r for r in metrics_rows if r["metrik"] in ("CER", "WER") and r["cakupan"] in ("Datar", "Melengkung") and r["nilai"] != ""]
    if cerwer:
        fig, ax = plt.subplots(figsize=(8.5, 5))
        labels = [f"{r['metrik']}\n{r['cakupan']}" for r in cerwer]
        vals = [float(r["nilai"]) for r in cerwer]
        ax.bar(labels, vals, color=["#2a9d8f" if r["metrik"] == "CER" else "#e9c46a" for r in cerwer])
        ax.set_ylabel("Rata-rata galat")
        ax.tick_params(labelsize=12)
        ax.grid(axis="y", alpha=.2)
        output_figure(out / f"{prefix}gambar_4_02_cer_wer_kondisi.png", fig)
    elif args.mode == "final" and (ROOT / "evaluation/results/evaluation_ocr/evaluation_metrics_summary.csv").exists():
        from plot_final_ocr_local import main as plot_final_ocr_local
        plot_final_ocr_local(out / f"{prefix}gambar_4_02_cer_wer_kondisi.png")
    else:
        fig, ax = plt.subplots(figsize=(8.5, 4.5))
        ax.text(.5, .5, "CER/WER per kondisi belum memiliki hasil tersimpan", ha="center", va="center", fontsize=15, wrap=True)
        ax.set_axis_off()
        output_figure(out / f"{prefix}gambar_4_02_cer_wer_kondisi.png", fig)

    # Confusion matrix heatmap.
    fig, ax = plt.subplots(figsize=(8, 6.2))
    mat = np.array([[matrix[(a, p)] for p in confusion_labels] for a in confusion_labels])
    ax.imshow(mat, cmap="Blues")
    ax.set_xticks(range(len(confusion_labels)), confusion_labels, rotation=28, ha="right", fontsize=10)
    ax.set_yticks(range(len(confusion_labels)), confusion_labels, fontsize=10)
    ax.set_xlabel("Kategori prediksi")
    ax.set_ylabel("Kategori ground truth")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, str(mat[i, j]), ha="center", va="center", fontsize=11, color="#111111")
    output_figure(out / f"{prefix}gambar_4_03_confusion_matrix_kategori.png", fig)

    # Expert category distributions before and after.
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    labels = [CATEGORY_LABEL[c] for c in CATEGORIES]
    x = np.arange(len(labels))
    width = .36
    ax.bar(x - width / 2, [before.get(c, 0) for c in CATEGORIES], width, label="Sebelum")
    ax.bar(x + width / 2, [after.get(c, 0) for c in CATEGORIES], width, label="Sesudah")
    ax.set_xticks(x, labels, fontsize=11)
    ax.set_ylabel("Jumlah entri")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=.2)
    output_figure(out / f"{prefix}gambar_4_04_kategori_kb_validasi.png", fig)

    # Four qualitative calibration examples: best and worst F1 by condition.
    qualitative = []
    rows_at = [r for r in detail if int(float(r["threshold"])) == args.error_threshold]
    for condition in ("datar", "melengkung"):
        candidates = [r for r in rows_at if r["category"] == condition]
        if not candidates:
            continue
        candidates.sort(key=lambda r: float(r["f1"]))
        qualitative.extend([(candidates[-1], "nilai F1 tertinggi dalam kondisi"), (candidates[0], "nilai F1 terendah dalam kondisi")])
    # Stable unique order, still at most four samples.
    seen = set()
    qualitative = [(r, label) for r, label in qualitative if not (r["filename"] in seen or seen.add(r["filename"]))][:4]
    captions = [
        "Gambar 4.01. Nilai F1 hasil kalibrasi pada beberapa threshold.",
        "Gambar 4.02. Nilai CER dan WER menurut kondisi permukaan kemasan.",
        "Gambar 4.03. Perbandingan kategori bahan pada ground truth dan hasil prediksi tersimpan.",
        "Gambar 4.04. Sebaran kategori knowledge base sebelum dan sesudah validasi ahli.",
    ]
    for idx, (row, descriptor) in enumerate(qualitative, start=5):
        filename = row["filename"]
        photo_path = RAW_PHOTOS / row["category"] / filename
        cache_text = composition_text(load_cache_text(cache_dir, filename))
        predicted = parse_list(row.get("predicted", "[]"))
        verdict = row.get("verdict", "Tidak tersedia")
        if not photo_path.exists():
            continue
        try:
            import cv2
            sys.path.insert(0, str(ROOT / "backend"))
            from app.preprocessing.pipeline import preprocess
            original = cv2.imread(str(photo_path))
            if original is None:
                continue
            original = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
            processed = preprocess(cv2.imread(str(photo_path)))
            if len(processed.shape) == 2:
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)
            else:
                processed = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        except Exception as exc:  # preserve other assets if image processing dependency is absent
            print(f"Panel dilewati untuk {filename}: {exc}")
            continue
        fig, axs = plt.subplots(2, 2, figsize=(12, 8))
        axs[0, 0].imshow(original)
        axs[0, 0].set_title("Foto asli", fontsize=14)
        axs[0, 1].imshow(processed, cmap="gray" if len(processed.shape) == 2 else None)
        axs[0, 1].set_title("Hasil preprocessing", fontsize=14)
        axs[1, 0].text(0, 1, textwrap.fill(cache_text[:1800], width=68), va="top", ha="left", fontsize=9, family="monospace", wrap=True)
        axs[1, 0].set_title("Teks OCR tersimpan", fontsize=14)
        axs[1, 1].text(0, 1, textwrap.fill("Bahan terdeteksi: " + (", ".join(predicted) or "tidak ada") + f"\nVerdict produk: {verdict}", width=42), va="top", ha="left", fontsize=11, wrap=True)
        axs[1, 1].set_title("Hasil klasifikasi tersimpan", fontsize=14)
        for ax in axs.flat:
            ax.axis("off")
        fig.tight_layout()
        imagename = f"{prefix}gambar_4_{idx:02d}_panel_{row['category']}_{'baik' if 'tertinggi' in descriptor else 'buruk'}.png"
        output_figure(out / imagename, fig)
        captions.append(f"Gambar 4.{idx:02d}. Foto {filename}, hasil preprocessing, teks OCR tersimpan, bahan terdeteksi, dan verdict produk.")

    captions_path = out / f"{prefix}captions.md"
    captions_path.write_text("\n".join(f"- {line}" for line in captions) + "\n", encoding="utf-8")

    # Save a provenance-aware snapshot. The current calibration grid predates
    # the current GT/KB hashes, so its candidate threshold is not frozen.
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        commit = None
    config = {
        "status": frozen_config["status"],
        "threshold": configured_threshold,
        "weights": frozen_config["weights"],
        "length_penalty": frozen_config["length_penalty"],
        "max_ocr_width": frozen_config["max_ocr_width"],
        "adaptive_threshold": frozen_config["adaptive_threshold"],
        "preprocessing_order": frozen_config["preprocessing_order"],
        "kb_version": frozen_config["kb_version"],
        "kb_sha256": frozen_config["kb_sha256"],
        "commit_hash": frozen_config["commit_hash"],
        "threshold_sumber": "evaluation/config_frozen.json",
        "versi_kb_hasil": "snapshot KB yang tercatat pada run colab_v4 (versi semantik belum diverifikasi)" if declared_kb_hash else "tidak diketahui",
        "hash_kb_hasil": declared_kb_hash,
        "hash_kb_saat_ini": kb_hash,
        "hash_gt_hasil": declared_gt_hash,
        "hash_gt_saat_ini": gt_hash,
        "provenance_cocok": not stale,
        "hash_commit_saat_ini": commit,
        "tanggal_proses": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "rata_rata_waktu_proses_per_foto_detik": None,
        "catatan_waktu": "Durasi per foto tidak tersedia dalam log tersimpan.",
        "dry_run_hanya_kalibrasi": dryrun,
        "jumlah_foto_kalibrasi_dalam_grid": len({r["filename"] for r in detail}),
        "hash_kode_grid_asal": run_manifest.get("input_manifest", {}).get("files_sha256", {}).get("evaluation/run_grid_search.py"),
    }
    (out / f"{prefix}chapter4_run_manifest.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    availability = [{"sumber": "grid_summary.csv", "status": "tersedia", "catatan": f"{len(summaries)} threshold tersimpan; provenance {'tidak cocok' if stale else 'cocok'}"},
                    {"sumber": "grid_detail.csv", "status": "tersedia", "catatan": f"{len(detail)} baris kalibrasi setelah pembatasan split"},
                    {"sumber": "CER/WER tersimpan", "status": "tersedia" if ocr_rows else "belum tersedia", "catatan": "Tidak dihitung ulang dalam dry run"},
                    {"sumber": "expert_validation_rows", "status": "tersedia" if expert_rows else "belum tersedia", "catatan": f"{len(expert_rows)} baris"},
                    {"sumber": "foto evaluasi", "status": "tidak dibuka", "catatan": "Hanya manifest split dibaca untuk jumlah per kondisi"}]

    tables = {
        "metrik": metrics_rows,
        "validasi_ahli": expert_table,
        "distribusi_split": split_table,
        "false_positive_teratas": fp_top,
        "false_negative_teratas": fn_top,
        "confusion_matrix": confusion_table,
        "ketersediaan_data": availability,
    }
    for name, rows in tables.items():
        write_table(out, f"tabel_{name}", rows, dryrun)
    add_workbook(out, tables, dryrun)
    print(f"Aset Chapter IV ditulis ke {out}")
    print(f"Dry run: {dryrun}; foto dalam grid calibration: {len({r['filename'] for r in detail})}; provenance cocok: {not stale}")
    print(f"Foto evaluasi dibuka/diproses: 0; CER/WER dihitung ulang: tidak")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dryrun", "final"), default="dryrun")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--calibration-split", type=Path, default=CAL_SPLIT)
    parser.add_argument("--evaluation-split", type=Path, default=EVAL_SPLIT)
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--kb-snapshot", type=Path, default=None)
    parser.add_argument("--expert-review", type=Path, default=EXPERT_REVIEW)
    parser.add_argument("--ocr-metrics", type=Path, default=None)
    parser.add_argument("--error-threshold", type=int, default=None)
    args = parser.parse_args()
    build_assets(args)


if __name__ == "__main__":
    main()
