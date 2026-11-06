"""Recompute calibration OCR metrics from stored OCR text; never invokes OCR."""
from __future__ import annotations

import csv
import json
import re
import string
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.tokenizer.tokenizer import extract_composition_section  # noqa: E402
from app.tokenizer.tokenizer import OPEN_MARKERS, _find_marker  # noqa: E402

SOURCE = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv"
DETAIL_OUT = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail_recomputed.csv"
SUMMARY_OUT = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_summary_recomputed.csv"
DIAGNOSTIC_OUT = ROOT / "evaluation/results/calibration_ocr_ablation/diagnostic_composition.md"


def normalize_for_metrics(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(" " if unicodedata.category(char).startswith("P") else char for char in text)
    return re.sub(r"\s+", " ", text).strip()


def local_edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Edit distance to the best contiguous hypothesis span; outer text is free."""
    previous = [0] * (len(hypothesis) + 1)  # free OCR prefix
    for ref_index, ref_item in enumerate(reference, start=1):
        current = [ref_index] + [0] * len(hypothesis)
        for hyp_index, hyp_item in enumerate(hypothesis, start=1):
            current[hyp_index] = min(
                previous[hyp_index] + 1,
                current[hyp_index - 1] + 1,
                previous[hyp_index - 1] + (ref_item != hyp_item),
            )
        previous = current
    return min(previous) if previous else len(reference)


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Standard Levenshtein distance without an optional Jiwer dependency."""
    previous = list(range(len(hypothesis) + 1))
    for ref_index, ref_item in enumerate(reference, start=1):
        current = [ref_index]
        for hyp_index, hyp_item in enumerate(hypothesis, start=1):
            current.append(min(
                previous[hyp_index] + 1,
                current[hyp_index - 1] + 1,
                previous[hyp_index - 1] + (ref_item != hyp_item),
            ))
        previous = current
    return previous[-1] if previous else len(reference)


def error_rate(reference: list[str], hypothesis: list[str]) -> float:
    return edit_distance(reference, hypothesis) / max(1, len(reference))


def local_cer_wer(reference: str, hypothesis: str) -> tuple[float, float]:
    ref_chars, hyp_chars = list(reference), list(hypothesis)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    cer = local_edit_distance(ref_chars, hyp_chars) / max(1, len(ref_chars))
    wer = local_edit_distance(ref_words, hyp_words) / max(1, len(ref_words))
    return cer, wer


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    if len(source_rows) != 240:
        raise ValueError(f"Expected 240 stored OCR rows, found {len(source_rows)}")

    details = []
    metrics_by_key = defaultdict(lambda: {
        "cer": [], "wer": [], "cer_full": [], "wer_full": [],
        "cer_full_normalized": [], "wer_full_normalized": [],
        "cer_local": [], "wer_local": [], "open_marker_missing": 0,
    })
    for row in source_rows:
        gt_full = row["ground_truth_text"]
        raw_ocr = row["ocr_text"]
        composition_ocr = extract_composition_section(raw_ocr)
        gt_norm = normalize_for_metrics(gt_full)
        raw_norm = normalize_for_metrics(raw_ocr)
        composition_norm = normalize_for_metrics(composition_ocr)
        full_cer = float(row.get("cer_teks_penuh") or row.get("cer") or 0)
        full_wer = float(row.get("wer_teks_penuh") or row.get("wer") or 0)
        gt_words, composition_words = gt_norm.split(), composition_norm.split()
        raw_words = raw_norm.split()
        composition_cer = error_rate(list(gt_norm), list(composition_norm))
        composition_wer = error_rate(gt_words, composition_words)
        full_normalized_cer = error_rate(list(gt_norm), list(raw_norm))
        full_normalized_wer = error_rate(gt_words, raw_words)
        local_cer, local_wer = local_cer_wer(gt_norm, raw_norm)
        open_marker_missing = _find_marker(raw_ocr.split(), OPEN_MARKERS) is None
        config = row["config_key"]
        condition = row["condition"]
        metrics_by_key[(config, condition)]["cer"].append(composition_cer)
        metrics_by_key[(config, condition)]["wer"].append(composition_wer)
        metrics_by_key[(config, condition)]["cer_full"].append(full_cer)
        metrics_by_key[(config, condition)]["wer_full"].append(full_wer)
        metrics_by_key[(config, condition)]["cer_full_normalized"].append(full_normalized_cer)
        metrics_by_key[(config, condition)]["wer_full_normalized"].append(full_normalized_wer)
        metrics_by_key[(config, condition)]["cer_local"].append(local_cer)
        metrics_by_key[(config, condition)]["wer_local"].append(local_wer)
        metrics_by_key[(config, condition)]["open_marker_missing"] += int(open_marker_missing)
        details.append({**row,
                        "cer_teks_penuh": full_cer,
                        "wer_teks_penuh": full_wer,
                        "cer_teks_penuh_normalized": full_normalized_cer,
                        "wer_teks_penuh_normalized": full_normalized_wer,
                        "teks_komposisi_ocr": composition_ocr,
                        "cer_komposisi": composition_cer,
                        "wer_komposisi": composition_wer,
                        "cer_lokal": local_cer,
                        "wer_lokal": local_wer,
                        "penanda_pembuka_terdeteksi": not open_marker_missing,
                        "normalisasi_metrik": "NFKC, casefold, tanda baca menjadi spasi, whitespace diringkas; diterapkan identik pada GT dan OCR"})

    summary = []
    configs = sorted({row["config_key"] for row in source_rows})
    for config in configs:
        for condition in ("keseluruhan", "datar", "melengkung"):
            conditions = ("datar", "melengkung") if condition == "keseluruhan" else (condition,)
            values = [metrics_by_key[(config, cond)] for cond in conditions]
            count = sum(len(item["cer"]) for item in values)
            mean = lambda key: sum(sum(item[key]) for item in values) / count if count else 0.0
            missing_markers = sum(item["open_marker_missing"] for item in values)
            summary.append({"config_key": config, "condition": condition, "n_photos": count,
                            "mean_cer_komposisi": mean("cer"), "mean_wer_komposisi": mean("wer"),
                            "mean_cer_teks_penuh": mean("cer_full"), "mean_wer_teks_penuh": mean("wer_full"),
                            "mean_cer_teks_penuh_normalized": mean("cer_full_normalized"),
                            "mean_wer_teks_penuh_normalized": mean("wer_full_normalized"),
                            "mean_cer_lokal": mean("cer_local"), "mean_wer_lokal": mean("wer_local"),
                            "penanda_pembuka_tidak_terdeteksi": missing_markers,
                            "normalisasi": "NFKC, casefold, tanda baca menjadi spasi, whitespace diringkas"})

    # Diagnostics: one flat sample, one curved sample, and the highest stored full-text CER.
    max_width_off = [row for row in source_rows if row["config_key"] == "width_2000_adaptive_off"]
    worst = max(source_rows, key=lambda row: float(row.get("cer_teks_penuh") or row["cer"]))
    flat = next(row for row in max_width_off if row["condition"] == "datar" and row["filename"] != worst["filename"])
    curved = next(row for row in max_width_off if row["condition"] == "melengkung"
                  and row["filename"] not in {flat["filename"], worst["filename"]})
    diagnostic_rows = []
    for role, row in (("sampel datar", flat), ("sampel melengkung", curved), ("CER teks penuh terburuk", worst)):
        comp = extract_composition_section(row["ocr_text"])
        gt_norm = normalize_for_metrics(row["ground_truth_text"])
        comp_norm = normalize_for_metrics(comp)
        diagnostic_rows.append({"role": role, "filename": row["filename"], "config_key": row["config_key"],
                                "gt_chars": len(row["ground_truth_text"]), "ocr_raw_chars": len(row["ocr_text"]),
                                "composition_chars": len(comp), "cer_full": row.get("cer_teks_penuh") or row["cer"],
                                "wer_full": row.get("wer_teks_penuh") or row["wer"],
                                "cer_raw_recomputed": error_rate(list(normalize_for_metrics(row["ground_truth_text"])),
                                                                  list(normalize_for_metrics(row["ocr_text"]))),
                                "wer_raw_recomputed": error_rate(normalize_for_metrics(row["ground_truth_text"]).split(),
                                                                  normalize_for_metrics(row["ocr_text"]).split()),
                                "cer_composition": error_rate(list(gt_norm), list(comp_norm)),
                                "wer_composition": error_rate(gt_norm.split(), comp_norm.split()),
                                "cer_local": local_cer_wer(gt_norm, normalize_for_metrics(row["ocr_text"]))[0],
                                "wer_local": local_cer_wer(gt_norm, normalize_for_metrics(row["ocr_text"]))[1],
                                "gt_excerpt": row["ground_truth_text"][:180],
                                "ocr_raw_excerpt": row["ocr_text"][:260],
                                "composition_excerpt": comp[:260]})

    write_csv(DETAIL_OUT, details)
    write_csv(SUMMARY_OUT, summary)
    missing_by_config_condition = []
    for config in configs:
        for condition in ("datar", "melengkung"):
            item = metrics_by_key[(config, condition)]
            missing_by_config_condition.append(
                f"| {config} | {condition} | {item['open_marker_missing']} dari 20 |"
            )
    lines = ["# Diagnosis metrik ablation", "",
             "Sumber: `ocr_ablation_detail.csv`; OCR tidak dijalankan ulang.",
             "Normalisasi baru diterapkan identik ke referensi dan hipotesis: Unicode NFKC, casefold, tanda baca diganti spasi, whitespace diringkas.",
             "Komposisi OCR dipotong dengan `extract_composition_section()` default produksi. GT tetap transkrip manual komposisi.",
             "Metrik lokal mengukur kesalahan baca OCR di wilayah komposisi yang paling cocok dengan GT; penghapusan OCR di awal/akhir tidak dikenai biaya. Metrik pasca ekstraksi mengukur kebersihan ekstraksi komposisi.",
             "CER/WER teks penuh lama mempertahankan perhitungan Jiwer sebelumnya; kolom `_normalized` disediakan untuk perbandingan ternormalisasi.", "",
             "## Penanda pembuka komposisi tidak terdeteksi", "",
             "| Konfigurasi | Kondisi | Foto |", "|---|---|---|", *missing_by_config_condition, ""]
    for item in diagnostic_rows:
        lines.extend([f"## {item['role']}: {item['filename']} ({item['config_key']})", "",
                      f"Panjang GT/OCR mentah/hasil ekstraksi: {item['gt_chars']} / {item['ocr_raw_chars']} / {item['composition_chars']} karakter.",
                      f"Metrik lama tersimpan CER/WER teks penuh: {float(item['cer_full']):.4f} / {float(item['wer_full']):.4f}.",
                      f"Metrik normalized mentah CER/WER: {item['cer_raw_recomputed']:.4f} / {item['wer_raw_recomputed']:.4f}.",
                      f"Metrik normalized komposisi CER/WER: {item['cer_composition']:.4f} / {item['wer_composition']:.4f}.",
                      f"Metrik lokal CER/WER: {item['cer_local']:.4f} / {item['wer_local']:.4f}.",
                      f"GT: `{item['gt_excerpt']}`", f"OCR mentah: `{item['ocr_raw_excerpt']}`",
                      f"Hasil ekstraksi: `{item['composition_excerpt']}`", ""])
    DIAGNOSTIC_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Detail: {DETAIL_OUT}\nRingkasan: {SUMMARY_OUT}\nDiagnosis: {DIAGNOSTIC_OUT}")


if __name__ == "__main__":
    main()
