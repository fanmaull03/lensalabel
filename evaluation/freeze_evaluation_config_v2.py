"""Create a superseding frozen evaluation configuration (v2) without touching v1.

Freeze v1 stays byte-identical on disk. This script writes
evaluation/config_frozen_v2.json plus its hash sidecar, records the selected
calibration configuration, and verifies every input hash it references.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1_CONFIG = ROOT / "evaluation/config_frozen.json"
V2_CONFIG = ROOT / "evaluation/config_frozen_v2.json"
V2_SHA = ROOT / "evaluation/config_frozen_v2.sha256"
GRID_ROOT = ROOT / "evaluation/results"
OCR_SECONDS_PER_PHOTO = {
    "width_1000_adaptive_off": 1.994,
    "width_1500_adaptive_off": 2.667,
    "width_2000_adaptive_off": 3.922,
    "width_1000_adaptive_on": 1.634,
    "width_1500_adaptive_on": 2.723,
    "width_2000_adaptive_on": 3.989,
}
TIE_BREAK_F1_DELTA = 0.01

# Freeze inputs whose bytes must be identical to what produced the v2 numbers.
FREEZE_INPUTS = (
    "backend/app/matching/fuzzy_matcher.py",
    "backend/app/matching/pair_blocks.py",
    "backend/app/matching/chemical_pair_blocks.json",
    "backend/app/matching/secondary_guards.py",
    "backend/app/classifier/rule_based.py",
    "backend/app/tokenizer/tokenizer.py",
    "backend/app/ocr/reader.py",
    "backend/app/preprocessing/pipeline.py",
    "backend/app/api/routes_identify.py",
    "evaluation/results/kb_v2_phase2/kb_v2_review.json",
    "dataset/ground_truth/calibration_ingredients_gt_v2_2.json",
    "evaluation/ground_truth/evaluation_gt_kb_v2_final.json",
    "dataset/ground_truth/transcripts.csv",
    "dataset/photo_manifest.csv",
    "evaluation/splits/evaluation_set.csv",
    "evaluation/splits/calibration_set.csv",
    "evaluation/build_eval_gt_kb_v2_aligned.py",
    "evaluation/validate_gt_kb_alignment.py",
    "evaluation/run_calibration_grid_v2.py",
    "evaluation/colab_evaluate_160_ocr.py",
    "evaluation/run_evaluate_160_parallel.py",
    "evaluation/evaluate_160_metrics.py",
    "evaluation/analyze_post_evaluation.py",
    "evaluation/package_final_evaluation_assets.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def selected_grid() -> dict:
    """Apply the frozen selection rule across all six recalibrated configurations."""
    candidates = []
    for directory in sorted(GRID_ROOT.glob("grid_width_*_postfix_v2")):
        config_key = directory.name.replace("grid_", "").replace("_postfix_v2", "")
        metadata_path = directory / "provisional_run_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.is_file() else {}
        threshold = int(metadata["threshold_selection"]["selected_threshold"])
        rows = list(csv.DictReader((directory / "grid_summary.csv").open(encoding="utf-8-sig")))
        overall = next(r for r in rows if r["cakupan"] == "Keseluruhan" and r["kategori"] == "semua"
                       and int(r["threshold"]) == threshold)
        hindari = next(r for r in rows if r["cakupan"] == "Keseluruhan" and r["kategori"] == "hindari"
                       and int(r["threshold"]) == threshold)
        candidates.append({
            "config_key": config_key,
            "threshold": threshold,
            "precision": float(overall["precision"]),
            "recall": float(overall["recall"]),
            "f1": float(overall["f1"]),
            "f1_ci95_low": float(overall["f1_ci95_low"]),
            "f1_ci95_high": float(overall["f1_ci95_high"]),
            "recall_hindari": float(hindari["recall"]),
            "ocr_seconds_per_photo": OCR_SECONDS_PER_PHOTO[config_key],
            "directory": directory,
            "threshold_reason": metadata["threshold_selection"].get("reason"),
        })
    if len(candidates) != 6:
        raise SystemExit(f"Jumlah konfigurasi kalibrasi tidak lengkap: {len(candidates)}")

    best_f1 = max(row["f1"] for row in candidates)
    near_best = [row for row in candidates if best_f1 - row["f1"] < TIE_BREAK_F1_DELTA]
    selected = min(near_best, key=lambda row: row["ocr_seconds_per_photo"])
    directory = selected.pop("directory")
    return {
        "selected": selected,
        "max_f1": best_f1,
        "near_best_configs": [row["config_key"] for row in near_best],
        "tie_break_applied": len(near_best) > 1,
        "summary_sha256": sha256(directory / "grid_summary.csv"),
        "detail_sha256": sha256(directory / "grid_detail.csv"),
        "bootstrap_sha256": sha256(directory / "bootstrap_ci.csv"),
        "directory": str(directory.relative_to(ROOT)).replace("\\", "/"),
    }


def verify_inputs() -> dict[str, str]:
    hashes, missing = {}, []
    for relative in FREEZE_INPUTS:
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
            continue
        hashes[relative] = sha256(path)
    if missing:
        raise SystemExit("Input freeze tidak lengkap: " + ", ".join(missing))
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="Tulis evaluation/config_frozen_v2.json dan sidecar hash.")
    args = parser.parse_args()

    v1_before = sha256(V1_CONFIG)
    v1 = json.loads(V1_CONFIG.read_text(encoding="utf-8-sig"))
    inputs = verify_inputs()
    grid = selected_grid()
    selected = grid["selected"]
    threshold = selected["threshold"]
    max_ocr_width = int(selected["config_key"].split("_")[1])
    adaptive_threshold = selected["config_key"].endswith("_on")

    config = {
        "status": "ready_to_freeze",
        "supersedes": {
            "path": "evaluation/config_frozen.json",
            "sha256": v1_before,
            "max_ocr_width": v1.get("max_ocr_width"),
            "threshold": v1.get("threshold"),
            "reason": "GT evaluasi diselaraskan ke KB v2 dan kode pasca-perbaikan dipakai ulang; kalibrasi ulang mengubah konfigurasi terpilih.",
        },
        "threshold": threshold,
        "weights": v1["weights"],
        "length_penalty": v1["length_penalty"],
        "max_ocr_width": max_ocr_width,
        "adaptive_threshold": adaptive_threshold,
        "preprocessing_order": v1["preprocessing_order"],
        "kb_version": v1["kb_version"],
        "kb_path": v1["kb_path"],
        "kb_sha256": inputs["evaluation/results/kb_v2_phase2/kb_v2_review.json"],
        "calibration_gt_path": v1["calibration_gt_path"],
        "calibration_gt_sha256": inputs["dataset/ground_truth/calibration_ingredients_gt_v2_2.json"],
        "evaluation_gt_path": "evaluation/ground_truth/evaluation_gt_kb_v2_final.json",
        "evaluation_gt_sha256": inputs["evaluation/ground_truth/evaluation_gt_kb_v2_final.json"],
        "evaluation_gt_notes": "Nama bahan kanonis KB v2; satu anotasi Licorice pada melengkung_096 dikecualikan atas keputusan ahli.",
        "blocked_pairs": v1["blocked_pairs"],
        "calibration_grid": {
            **selected,
            "max_f1_across_configs": grid["max_f1"],
            "near_best_configs": grid["near_best_configs"],
            "tie_break_applied": grid["tie_break_applied"],
            "selection_rule": (
                "F1 tingkat bahan tertinggi; bila selisih F1 antarkonfigurasi < 0,01, "
                "pilih waktu OCR per foto yang lebih rendah"
            ),
            "threshold_rule": "F1 maksimum per konfigurasi; tie-break recall Hindari bila selisih < 0,01",
        },
        "transcripts_sha256": inputs["dataset/ground_truth/transcripts.csv"],
        "freeze_inputs_sha256": inputs,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_at_creation": git("rev-parse", "HEAD"),
        "pending_steps": [
            f"Jalankan ulang OCR 160 foto dengan konfigurasi {selected['config_key']} di Colab.",
            "Regenerasi prediksi, metrik, analisis, dan aset BAB IV.",
        ],
    }

    print(json.dumps({"confirm": args.confirm, "selected": config["calibration_grid"], "v1_untouched": sha256(V1_CONFIG) == v1_before}, ensure_ascii=False, indent=2))
    if not args.confirm:
        print("Dry run: tidak ada file yang ditulis. Jalankan dengan --confirm.")
        return
    if V2_CONFIG.exists() or V2_SHA.exists():
        raise SystemExit("config_frozen_v2 sudah ada; tidak akan ditimpa.")
    config["status"] = "frozen"
    V2_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    V2_SHA.write_text(sha256(V2_CONFIG) + "  config_frozen_v2.json\n", encoding="ascii")
    if sha256(V1_CONFIG) != v1_before:
        raise SystemExit("PERINGATAN: config_frozen.json v1 berubah. Periksa manual.")
    print(json.dumps({"written": str(V2_CONFIG.relative_to(ROOT)), "sha256": sha256(V2_CONFIG),
                      "v1_untouched": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
