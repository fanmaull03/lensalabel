"""Validate that every final evaluation-GT annotation resolves to KB v2."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GT = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
DEFAULT_KB = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
DEFAULT_SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
DEFAULT_REVIEW = ROOT / "evaluation/results/gt_v2_alignment/validasi_pemetaan_gt_ke_kb_v2.xlsx"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_split(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["filename"] for row in csv.DictReader(stream)}


def load_kb(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    document = load_json(path)
    entries = document.get("ingredients", document)
    by_name = {str(entry["standard_name"]): entry for entry in entries}
    by_id = {str(entry["new_entry_id"]): entry for entry in entries}
    return by_name, by_id


def load_review_decisions(path: Path) -> tuple[dict[str, str], list[str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "validasi_kasus" not in workbook.sheetnames:
            raise ValueError("Sheet validasi_kasus tidak ditemukan.")
        sheet = workbook["validasi_kasus"]
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        required = {"id_kasus", "keputusan_final"}
        missing = required - set(headers)
        if missing:
            raise ValueError(f"Kolom review tidak lengkap: {sorted(missing)}")
        rows = [dict(zip(headers, values)) for values in sheet.iter_rows(min_row=2, values_only=True)
                if any(value is not None for value in values)]
    finally:
        workbook.close()
    decisions = {str(row["id_kasus"]): str(row.get("keputusan_final") or "").strip()
                 for row in rows}
    pending = [case_id for case_id, decision in decisions.items() if not decision]
    return decisions, pending


def validate(gt: dict, kb_by_name: dict[str, dict], allowed_files: set[str]) -> dict:
    errors: list[dict] = []
    categories = Counter()
    total_items = 0
    for filename, record in gt.items():
        if filename not in allowed_files:
            errors.append({"filename": filename, "error": "foto_di_luar_split"})
        for item in record.get("ingredients", []):
            total_items += 1
            name = str(item.get("standard_name") or "")
            category = str(item.get("category") or "").casefold()
            entry = kb_by_name.get(name)
            if entry is None:
                errors.append({"filename": filename, "standard_name": name,
                               "error": "nama_tidak_ada_di_kb_v2"})
                continue
            kb_category = str(entry.get("category") or "").casefold()
            if category != kb_category:
                errors.append({"filename": filename, "standard_name": name,
                               "gt_category": category, "kb_category": kb_category,
                               "error": "kategori_gt_tidak_sama_dengan_kb_v2"})
            categories[category] += 1
    missing_files = sorted(allowed_files - set(gt))
    if missing_files:
        errors.append({"error": "foto_split_tidak_ada_di_gt", "count": len(missing_files),
                       "examples": missing_files[:10]})
    if len(gt) != len(allowed_files):
        errors.append({"error": "jumlah_foto_gt_tidak_sama_dengan_split",
                       "gt": len(gt), "split": len(allowed_files)})
    return {
        "photos": len(gt),
        "expected_photos": len(allowed_files),
        "items": total_items,
        "categories": dict(categories),
        "errors": errors,
        "valid": not errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", type=Path, default=DEFAULT_GT)
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW,
                        help="Workbook validasi ahli. Dipakai untuk memeriksa kelengkapan keputusan bila file tersedia.")
    parser.add_argument("--require-review", action="store_true",
                        help="Gagal jika workbook review tidak ada atau keputusan ahli belum lengkap.")
    args = parser.parse_args()

    if args.require_review and not args.review.is_file():
        raise SystemExit(f"Workbook review belum tersedia: {args.review}")
    if args.review.is_file():
        decisions, pending = load_review_decisions(args.review)
    else:
        decisions, pending = {}, []
    if args.require_review and pending:
        raise SystemExit("Keputusan ahli belum diisi untuk: " + ", ".join(pending))

    result = validate(load_json(args.gt), load_kb(args.kb)[0], load_split(args.split))
    result["ground_truth_path"] = str(args.gt.relative_to(ROOT)).replace("\\", "/")
    result["ground_truth_sha256"] = sha256(args.gt)
    result["knowledge_base_path"] = str(args.kb.relative_to(ROOT)).replace("\\", "/")
    result["knowledge_base_sha256"] = sha256(args.kb)
    result["review_decisions"] = decisions
    result["pending_review_cases"] = pending
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]:
        raise SystemExit("Ground truth tidak selaras dengan KB v2.")


if __name__ == "__main__":
    main()
