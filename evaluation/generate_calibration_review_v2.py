"""Regenerasi GT kalibrasi dan review v2 dengan kontinuitas keputusan v1.

Pencocokan/negasi memakai fungsi yang sudah ada. Workbook v1 hanya dibaca.
Gunakan --previous-review PATH untuk menunjuk workbook manual yang sudah diisi.
--regenerate-only menyelesaikan strict/lenient sambil menunggu workbook tersebut.
--fresh-review memulai review baru tanpa memakai keputusan/kandidat v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.generate_calibration_review import (
    CALIB_SPLIT_PATH, STRICT_GT_PATH, TRANSCRIPTS_PATH, build_workbook,
    exact_changes, json_bytes, read_rows, regenerate,
)
from app.matching.fuzzy_matcher import load_knowledge_base, load_knowledge_base_from_json

V1_PATH = ROOT / "dataset/ground_truth/calibration_review.xlsx"
V2_PATH = ROOT / "dataset/ground_truth/calibration_review_v2.xlsx"
SUMMARY_PATH = ROOT / "dataset/ground_truth/calibration_regeneration_v2_summary.json"
PENDING_PATH = ROOT / "evaluation/results/calibration_v2_candidates.json"
KEY_FIELDS = ("filename", "standard_name", "matched_variant")
REVIEW_FIELDS = (
    "filename", "standard_name", "category", "sumber", "matched_variant",
    "potongan_teks", "keputusan", "status_vs_v1",
)


def candidate_key(row: dict) -> tuple[str, str, str]:
    # Tanpa lowercase, alias nama lama, atau normalisasi kunci: harus PERSIS.
    values = tuple(row.get(field) for field in KEY_FIELDS)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"Kunci kandidat tidak lengkap: {dict(zip(KEY_FIELDS, values))}")
    return values


def read_previous_review(path: Path) -> list[dict]:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        if "kandidat_review" not in workbook.sheetnames:
            raise ValueError("Workbook v1 tidak memiliki sheet kandidat_review.")
        iterator = workbook["kandidat_review"].iter_rows(values_only=True)
        headers = next(iterator, ())
        required = set(REVIEW_FIELDS) - {"status_vs_v1"}
        missing = required - set(headers)
        if missing:
            raise ValueError(f"Workbook v1 tidak memiliki kolom {', '.join(sorted(missing))}; "
                             "keputusan tidak dapat dibawa menggunakan kunci persis.")
        rows, seen = [], set()
        for index, values in enumerate(iterator, 2):
            if not any(value is not None for value in values):
                continue
            row = dict(zip(headers, values))
            key = candidate_key(row)
            if key in seen:
                raise ValueError(f"Kunci kandidat v1 duplikat pada baris {index}: {key}")
            seen.add(key)
            decision = str(row["keputusan"]).strip().upper() if row["keputusan"] is not None else ""
            if decision not in {"", "Y", "N"}:
                raise ValueError(f"Keputusan v1 bukan Y/N pada baris {index}: {decision}")
            row["keputusan"] = decision
            rows.append(row)
        return rows
    finally:
        workbook.close()


def carry_decisions(candidates: list[dict], previous: list[dict]) -> tuple[list[dict], dict]:
    old_by_key = {}
    for row in previous:
        key = candidate_key(row)
        if key in old_by_key:
            raise ValueError(f"Kunci kandidat v1 duplikat: {key}")
        old_by_key[key] = row
    current_keys = set()
    output, carried = [], []
    for candidate in candidates:
        key = candidate_key(candidate)
        if key in current_keys:
            raise ValueError(f"Kunci kandidat baru duplikat: {key}")
        current_keys.add(key)
        row = dict(candidate)
        previous_row = old_by_key.get(key)
        decision = previous_row.get("keputusan", "") if previous_row else ""
        if decision in {"Y", "N"}:
            row["keputusan"] = decision
            row["status_vs_v1"] = "SAMA_DIBAWA_OTOMATIS"
            carried.append(key)
        else:
            row["keputusan"] = ""
            row["status_vs_v1"] = "BARU"
        output.append(row)
    lost = []
    for key, previous_row in old_by_key.items():
        if key not in current_keys:
            row = dict(previous_row)
            row["status_vs_v1"] = "HILANG"
            lost.append(row)
    output.extend(lost)
    return output, {
        "previous_candidate_total": len(previous),
        "previous_decided_total": sum(row.get("keputusan") in {"Y", "N"} for row in previous),
        "candidate_total": len(candidates), "carried_total": len(carried),
        "needs_new_decision_total": len(candidates) - len(carried),
        "lost_total": len(lost), "workbook_row_total": len(output),
        "carried_keys": [list(key) for key in carried],
        "lost_keys": [list(candidate_key(row)) for row in lost],
    }


def build_v2_workbook(strict_gt: dict, candidates: list[dict], review: list[dict],
                      summary: dict, changes: list[dict]):
    workbook = build_workbook(strict_gt, candidates, summary, changes)
    del workbook["kandidat_review"]
    sheet = workbook.create_sheet("kandidat_review", 0)
    sheet.append(REVIEW_FIELDS)
    for row in review:
        sheet.append([row.get(field, "") for field in REVIEW_FIELDS])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24465A")
    widths = (25, 75, 18, 24, 60, 120, 16, 30)
    for column, width in zip(sheet.columns, widths):
        sheet.column_dimensions[column[0].column_letter].width = width
    for cells in sheet.iter_rows(min_row=2):
        status = cells[-1].value
        color = {"BARU": "FFF2CC", "SAMA_DIBAWA_OTOMATIS": "E2F0D9", "HILANG": "E7E6E6"}[status]
        for cell in cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor=color)
    validation = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    validation.showErrorMessage = True
    validation.error = "Isi Y atau N."
    sheet.add_data_validation(validation)
    if candidates:
        validation.add(f"G2:G{len(candidates) + 1}")
    notes = workbook["ringkasan"]
    for field in ("previous_review_path", "previous_review_sha256", "previous_candidate_total",
                  "previous_decided_total", "carried_total", "needs_new_decision_total", "lost_total"):
        notes.append([field, summary[field]])
    notes.append(["kunci keputusan", "(filename, standard_name, matched_variant) harus persis sama; nama yang berubah tidak otomatis dipetakan."])
    notes.append(["HILANG", "Baris historis v1, bukan kandidat aktif untuk digabungkan. Keputusan lama dipertahankan untuk audit."])
    return workbook


def load_baseline() -> dict:
    # Baseline KB 68 yang sudah dicadangkan pada regenerasi pertama.
    for path in sorted((ROOT / "evaluation/results/calibration_annotation_backups").glob("*/calibration_ingredients_gt.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if sum(len(info["ingredients"]) for info in data.values()) == 221:
            return data
    raise FileNotFoundError("Baseline 221 anotasi tidak ditemukan pada cadangan.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-review", type=Path, default=V1_PATH)
    parser.add_argument("--kb-json", type=Path)
    parser.add_argument("--regenerate-only", action="store_true")
    parser.add_argument("--fresh-review", action="store_true", help="Semua kandidat BARU; abaikan review v1.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.regenerate_only and args.fresh_review:
        parser.error("Pilih --regenerate-only atau --fresh-review, bukan keduanya.")
    if args.kb_json:
        kb = load_knowledge_base_from_json(args.kb_json)
    else:
        from app.db.session import SessionLocal
        with SessionLocal() as session:
            kb = load_knowledge_base(session)
    split = read_rows(CALIB_SPLIT_PATH)
    strict_gt, candidates = regenerate(split, read_rows(TRANSCRIPTS_PATH), kb)
    if len(strict_gt) != 40 or Counter(row["category"] for row in split) != {"datar": 20, "melengkung": 20}:
        raise ValueError("Subset kalibrasi harus 40 foto: 20 datar dan 20 melengkung.")
    baseline = load_baseline()
    exact = [ingredient for info in strict_gt.values() for ingredient in info["ingredients"]]
    changes = exact_changes(baseline, strict_gt, kb)
    summary = {
        "n_photos": len(strict_gt), "kb_ingredients": len({entry["ingredient_id"] for entry in kb}),
        "kb_variants": len(kb), "kb_sha256": hashlib.sha256(json_bytes(kb)).hexdigest(),
        "old_exact_total": 221, "exact_total": len(exact),
        "exact_by_category": dict(Counter(row["category"] for row in exact)),
        "candidate_total": len(candidates),
        "candidates_by_category": dict(Counter(row["category"] for row in candidates)),
        "candidates_by_source": dict(Counter(row["sumber"] for row in candidates)),
        "changes_by_type": dict(Counter(row["change"] for row in changes)),
    }
    workbook = None
    if args.regenerate_only:
        summary["continuity_status"] = "pending_previous_review"
    else:
        previous = [] if args.fresh_review else read_previous_review(args.previous_review)
        if not args.fresh_review and not any(row["keputusan"] in {"Y", "N"} for row in previous):
            raise ValueError("Workbook v1 yang dipilih tidak memiliki keputusan Y/N. "
                             "Tunjuk workbook manual yang sudah diisi menggunakan --previous-review.")
        review, continuity = carry_decisions(candidates, previous)
        summary.update(continuity)
        summary["continuity_status"] = "complete"
        summary["fresh_review"] = args.fresh_review
        summary["previous_review_path"] = "" if args.fresh_review else str(args.previous_review.resolve())
        summary["previous_review_sha256"] = "" if args.fresh_review else hashlib.sha256(args.previous_review.read_bytes()).hexdigest()
        workbook = build_v2_workbook(strict_gt, candidates, review, summary, changes)
    if not args.dry_run:
        backup = ROOT / "evaluation/results/calibration_annotation_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for path in (STRICT_GT_PATH, V2_PATH, SUMMARY_PATH):
            if path.exists():
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup / path.name)
        STRICT_GT_PATH.write_bytes(json_bytes(strict_gt))
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        PENDING_PATH.write_bytes(json_bytes({"summary": summary, "candidates": candidates, "knowledge_base": kb}))
        if workbook:
            workbook.save(V2_PATH)
            SUMMARY_PATH.write_bytes(json_bytes(summary))
            print(f"Review v2: {V2_PATH}")
        print(f"Strict GT: {STRICT_GT_PATH}\nCadangan: {backup}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
