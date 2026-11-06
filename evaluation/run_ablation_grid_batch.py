"""Run calibration matcher grids for every stored OCR ablation configuration.

Consumes saved OCR text only. Each configuration gets independent grid outputs;
the matcher score caches are retained between configurations in this process.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DETAIL = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail_recomputed.csv"
METRICS = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_summary_recomputed.csv"
DETAIL_ROWS = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail_recomputed.csv"
OUT = ROOT / "evaluation/results/calibration_ocr_ablation"
GT_V2_1 = ROOT / "dataset/ground_truth/calibration_ingredients_gt_v2_1.json"
GT_TAG = "gt_v2_1"
WIDTHS = (1000, 1500, 2000)
ADAPTIVE = ("off", "on")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not DETAIL.exists() or not METRICS.exists() or not DETAIL_ROWS.exists():
        raise FileNotFoundError("Jalankan recompute_ablation_metrics.py lebih dahulu.")
    if not GT_V2_1.exists():
        raise FileNotFoundError(f"GT v2.1 belum tersedia: {GT_V2_1}")
    import evaluation.run_calibration_grid_v2 as grid

    original_argv = sys.argv
    try:
        for width in WIDTHS:
            for adaptive in ADAPTIVE:
                config_key = f"width_{width}_adaptive_{adaptive}"
                print(f"\n=== Grid {config_key} ===", flush=True)
                sys.argv = ["run_calibration_grid_v2.py", "--ocr-ablation-detail", str(DETAIL),
                            "--max-ocr-width", str(width), "--adaptive-threshold", adaptive,
                            "--gt-json", str(GT_V2_1), "--output-suffix", GT_TAG]
                grid.main()
    finally:
        sys.argv = original_argv

    metric_rows = {row["config_key"]: row for row in read_csv(METRICS)
                   if row["condition"] == "keseluruhan"}
    detail_rows = read_csv(DETAIL_ROWS)
    result_rows = []
    for width in WIDTHS:
        for adaptive in ADAPTIVE:
            config_key = f"width_{width}_adaptive_{adaptive}"
            directory = ROOT / f"evaluation/results/grid_{config_key}_{GT_TAG}"
            summary = read_csv(directory / "grid_summary.csv")
            bootstrap = read_csv(directory / "bootstrap_ci.csv")
            metadata = json.loads((directory / "provisional_run_metadata.json").read_text(encoding="utf-8"))
            selected = int(metadata["threshold_selection"]["selected_threshold"])
            overall = next(row for row in summary if int(row["threshold"]) == selected
                           and row["cakupan"] == "Keseluruhan" and row["kategori"] == "semua")
            hindari = next(row for row in summary if int(row["threshold"]) == selected
                           and row["cakupan"] == "Keseluruhan" and row["kategori"] == "hindari")
            ci = next(row for row in bootstrap if int(row["threshold"]) == selected)
            matching_times = [float(row["ocr_runtime_seconds"]) for row in detail_rows
                              if row["config_key"] == config_key]
            metric = metric_rows[config_key]
            result_rows.append({
                "config_key": config_key, "max_ocr_width": width,
                "adaptive_threshold": adaptive == "on", "selected_threshold": selected,
                "precision_total": float(overall["precision"]), "recall_total": float(overall["recall"]),
                "f1_total": float(overall["f1"]), "recall_hindari": float(hindari["recall"]),
                "f1_ci95_low": float(ci["f1_ci95_low"]), "f1_ci95_high": float(ci["f1_ci95_high"]),
                "hindari_recall_ci95_low": float(ci["hindari_recall_ci95_low"]),
                "hindari_recall_ci95_high": float(ci["hindari_recall_ci95_high"]),
                "cer_komposisi_mean": float(metric["mean_cer_komposisi"]),
                "wer_komposisi_mean": float(metric["mean_wer_komposisi"]),
                "ocr_runtime_mean_seconds_per_photo": sum(matching_times) / len(matching_times),
                "threshold_selection_reason": metadata["threshold_selection"]["reason"],
            })

    highest_f1 = max(row["f1_total"] for row in result_rows)
    finalists = [row for row in result_rows if highest_f1 - row["f1_total"] < 0.01]
    chosen = min(finalists, key=lambda row: (row["ocr_runtime_mean_seconds_per_photo"],
                                             -row["f1_total"], row["config_key"]))
    if len(finalists) == 1:
        reason = f"F1 terpilih tertinggi dan unik ({highest_f1:.4f})."
    elif chosen["f1_total"] < highest_f1:
        reason = (f"F1 {chosen['f1_total']:.4f} berjarak <0,01 dari maksimum {highest_f1:.4f}; "
                  f"waktu OCR rata-rata paling rendah di antara konfigurasi kandidat "
                  f"({chosen['ocr_runtime_mean_seconds_per_photo']:.3f} detik/foto).")
    else:
        reason = (f"F1 tertinggi {highest_f1:.4f}; konfigurasi ini paling cepat di antara konfigurasi "
                  f"dengan F1 berjarak <0,01 ({chosen['ocr_runtime_mean_seconds_per_photo']:.3f} detik/foto).")
    for row in result_rows:
        row["configuration_selection_status"] = "TERPILIH" if row["config_key"] == chosen["config_key"] else ""
        row["configuration_selection_reason"] = reason if row["config_key"] == chosen["config_key"] else ""
    write_csv(OUT / f"ablation_grid_comparison_{GT_TAG}.csv", result_rows)
    choice = {"selected_config": chosen["config_key"], "selection_rule":
              "F1 maksimum pada threshold terpilih; bila selisih F1 < 0.01, pilih waktu OCR rata-rata lebih rendah",
              "reason": reason, "threshold": chosen["selected_threshold"],
              "f1_total": chosen["f1_total"], "recall_hindari": chosen["recall_hindari"],
              "bootstrap_f1_ci95": [chosen["f1_ci95_low"], chosen["f1_ci95_high"]],
              "mean_ocr_seconds_per_photo": chosen["ocr_runtime_mean_seconds_per_photo"]}
    (OUT / f"ablation_grid_selection_{GT_TAG}.json").write_text(json.dumps(choice, ensure_ascii=False, indent=2) + "\n",
                                                                  encoding="utf-8")
    print("\nKonfigurasi OCR terpilih: " + json.dumps(choice, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
