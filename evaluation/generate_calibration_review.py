"""Regenerasi exact GT dan kandidat review lenient untuk subset kalibrasi.

Dari root proyek: backend/.venv/Scripts/python.exe evaluation/generate_calibration_review.py
Kandidat lenient tetap menunggu keputusan Y/N pada workbook sebelum merge final.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from dotenv import load_dotenv
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env", override=False)

from app.matching.fuzzy_matcher import load_knowledge_base, load_knowledge_base_from_json
from app.tokenizer.tokenizer import extract_composition_section
from evaluation.calibration_annotations import (
    TERM_MAP, is_word_fuzzy_match, normalize_words, review_rows, strict_ingredients,
)

STRICT_GT_PATH = REPO_ROOT / "dataset/ground_truth/calibration_ingredients_gt.json"
CALIB_SPLIT_PATH = REPO_ROOT / "evaluation/splits/calibration_set.csv"
TRANSCRIPTS_PATH = REPO_ROOT / "dataset/ground_truth/transcripts.csv"
OUT_XLSX = REPO_ROOT / "dataset/ground_truth/calibration_review.xlsx"
SUMMARY_PATH = REPO_ROOT / "dataset/ground_truth/calibration_regeneration_summary.json"
KB_SNAPSHOT_PATH = REPO_ROOT / "evaluation/kb_snapshot.json"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def regenerate(split: list[dict], transcripts: list[dict], kb: list[dict]) -> tuple[dict, list[dict]]:
    if len({row["filename"] for row in split}) != len(split):
        raise ValueError("Ada filename duplikat pada split kalibrasi.")
    if len({row["filename"] for row in transcripts}) != len(transcripts):
        raise ValueError("Ada filename duplikat pada transkripsi.")
    if not kb:
        raise ValueError("Knowledge base kosong.")
    transcript_by_name = {row["filename"]: row for row in transcripts}
    strict_gt, candidates = {}, []
    for row in split:
        filename = row["filename"]
        transcript = transcript_by_name[filename]
        if row["category"] != transcript["category"]:
            raise ValueError(f"Kategori foto berbeda antara split/transkripsi: {filename}")
        text = transcript["ground_truth_text"]
        if not text.strip():
            raise ValueError(f"Transkripsi kosong: {filename}")
        composition = extract_composition_section(text)
        ingredients = strict_ingredients(composition, kb)
        strict_gt[filename] = {
            "filename": filename, "category": row["category"],
            "ground_truth_text": text, "composition_text": composition,
            "ingredients": ingredients,
        }
        candidates.extend(review_rows(filename, composition, ingredients, kb))
    return strict_gt, candidates


def exact_changes(old_gt: dict, strict_gt: dict, kb: list[dict]) -> list[dict]:
    from app.db.seed_knowledge_base import LEGACY_NAMES
    known_names = {entry["standard_name"] for entry in kb}
    changes = []
    for filename, info in strict_gt.items():
        old = old_gt.get(filename, {}).get("ingredients", [])
        current = {ingredient["standard_name"]: ingredient for ingredient in info["ingredients"]}
        translated = {}
        for ingredient in old:
            name = LEGACY_NAMES.get(ingredient["standard_name"], ingredient["standard_name"])
            translated.setdefault(name, []).append(ingredient)
        for name, ingredient in current.items():
            previous = translated.get(name, [])
            if not previous:
                changes.append({"filename": filename, "change": "ditambahkan",
                                "old_name": "", "new_name": name, "old_category": "",
                                "new_category": ingredient["category"]})
            elif any(item["standard_name"] != name or item["category"] != ingredient["category"] for item in previous):
                changes.append({"filename": filename, "change": "nama/kategori_diperbarui",
                                "old_name": " | ".join(item["standard_name"] for item in previous),
                                "new_name": name, "old_category": " | ".join(sorted({item["category"] for item in previous})),
                                "new_category": ingredient["category"]})
        for name, previous in translated.items():
            if name not in current:
                changes.append({"filename": filename,
                                "change": "bahan_keluar_kb" if name not in known_names else "tidak_exact_di_kb_baru",
                                "old_name": " | ".join(item["standard_name"] for item in previous),
                                "new_name": name if name in known_names else "",
                                "old_category": " | ".join(sorted({item["category"] for item in previous})),
                                "new_category": ""})
    return changes


def build_workbook(strict_gt: dict, candidates: list[dict], summary: dict, changes: list[dict]):
    workbook = openpyxl.Workbook()
    review = workbook.active
    review.title = "kandidat_review"
    # Enam kolom pertama dipertahankan agar merge_reviewed_gt.py tetap kompatibel.
    candidate_fields = ["filename", "standard_name", "category", "sumber", "potongan_teks", "keputusan",
                        "ingredient_id", "matched_variant", "matched_text"]
    review.append(candidate_fields)
    for row in candidates:
        review.append([row[field] for field in candidate_fields])
    decision = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    decision.errorTitle = "Keputusan tidak valid"
    decision.error = "Isi Y untuk menerima atau N untuk menolak kandidat."
    decision.showErrorMessage = True
    review.add_data_validation(decision)
    if candidates:
        decision.add(f"F2:F{len(candidates) + 1}")

    strict = workbook.create_sheet("strict_gt_referensi")
    strict_fields = ["filename", "standard_name", "category", "matched_variant"]
    strict.append(strict_fields)
    for filename, info in strict_gt.items():
        for ingredient in info["ingredients"]:
            strict.append([filename, ingredient["standard_name"], ingredient["category"], ingredient["matched_variant"]])

    delta = workbook.create_sheet("perubahan_exact")
    delta_fields = ["filename", "change", "old_name", "new_name", "old_category", "new_category"]
    delta.append(delta_fields)
    for row in changes:
        delta.append([row[field] for field in delta_fields])

    notes = workbook.create_sheet("ringkasan")
    notes.append(["item", "nilai"])
    for key in ["n_photos", "kb_ingredients", "kb_variants", "old_exact_total", "exact_total", "candidate_total", "kb_sha256"]:
        notes.append([key, summary[key]])
    for group in ["exact_by_category", "candidates_by_category", "candidates_by_source", "changes_by_type"]:
        for key, value in summary[group].items():
            notes.append([f"{group}: {key}", value])
    notes.append(["exact", "Nama/sinonim KB utuh, tidak peka huruf besar/kecil, batas kata dan negasi lokal diperiksa."])
    notes.append(["lenient", "Normalisasi istilah, jarak Levenshtein <= 1 untuk kata >= 6 karakter, maksimal 3 kata sisipan."])
    notes.append(["keputusan", "Isi Y/N di kandidat_review; kandidat tidak otomatis dimasukkan ke anotasi final."])
    notes.append(["nama spesifik", "Alias umum di dalam alias bahan lebih lengkap diprioritaskan ke bahan spesifik; kandidat umum dapat tetap muncul untuk review."])
    notes.append(["ruang lingkup exact", "Exact adalah kecocokan teks; konteks seperti perisa buah tetap perlu ditelaah saat review anotasi."])
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24465A")
        for column in sheet.columns:
            header = column[0].value
            width = 110 if header in ["potongan_teks", "nilai"] else 68 if header in ["standard_name", "old_name", "new_name", "matched_variant", "matched_text"] else 26
            sheet.column_dimensions[column[0].column_letter].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    return workbook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-json", type=Path, help="Gunakan snapshot KB; default database aktif.")
    parser.add_argument("--dry-run", action="store_true", help="Hitung hasil tanpa menulis artefak.")
    review_version = parser.add_mutually_exclusive_group()
    review_version.add_argument("--review-v3", action="store_true", help="Buat v3 dari keputusan v2; tidak menulis strict GT, KB, atau workbook lama.")
    review_version.add_argument("--review-v4", action="store_true", help="Buat v4, tandai ambigu taksonomi, pertahankan semua Y v2; strict GT/KB tetap.")
    args = parser.parse_args()
    if args.kb_json:
        kb = load_knowledge_base_from_json(args.kb_json)
    else:
        from app.db.session import SessionLocal
        with SessionLocal() as session:
            kb = load_knowledge_base(session)
    split, transcripts = read_rows(CALIB_SPLIT_PATH), read_rows(TRANSCRIPTS_PATH)
    strict_gt, candidates = regenerate(split, transcripts, kb)
    if args.review_v3:
        from evaluation.calibration_review_v3 import write_review_v3
        write_review_v3(strict_gt, candidates, kb, dry_run=args.dry_run)
        return
    if args.review_v4:
        from evaluation.calibration_review_v4 import write_review_v4
        write_review_v4(strict_gt, candidates, kb, dry_run=args.dry_run)
        return
    old_gt = json.loads(STRICT_GT_PATH.read_text(encoding="utf-8-sig")) if STRICT_GT_PATH.exists() else {}
    changes = exact_changes(old_gt, strict_gt, kb)
    exact = [ingredient for info in strict_gt.values() for ingredient in info["ingredients"]]
    summary = {
        "n_photos": len(strict_gt), "photos_by_category": dict(Counter(row["category"] for row in split)),
        "kb_ingredients": len({entry["ingredient_id"] for entry in kb}), "kb_variants": len(kb),
        "kb_sha256": hashlib.sha256(json_bytes(kb)).hexdigest(),
        "old_exact_total": sum(len(info["ingredients"]) for info in old_gt.values()),
        "exact_total": len(exact), "exact_by_category": dict(Counter(row["category"] for row in exact)),
        "candidate_total": len(candidates), "candidates_by_category": dict(Counter(row["category"] for row in candidates)),
        "candidates_by_source": dict(Counter(row["sumber"] for row in candidates)),
        "changes_by_type": dict(Counter(row["change"] for row in changes)),
        "changes": changes,
    }
    if not args.dry_run:
        workbook = build_workbook(strict_gt, candidates, summary, changes)
        backup_dir = REPO_ROOT / "evaluation/results/calibration_annotation_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for path in [STRICT_GT_PATH, OUT_XLSX, SUMMARY_PATH, KB_SNAPSHOT_PATH]:
            if path.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_dir / path.name)
        summary["backup_directory"] = str(backup_dir.relative_to(REPO_ROOT))
        OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(OUT_XLSX)
        STRICT_GT_PATH.write_bytes(json_bytes(strict_gt))
        KB_SNAPSHOT_PATH.write_bytes(json_bytes(kb))
        SUMMARY_PATH.write_bytes(json_bytes(summary))
        print(f"Exact GT: {STRICT_GT_PATH}\nReview: {OUT_XLSX}\nSnapshot KB: {KB_SNAPSHOT_PATH}")
        print(f"Cadangan hasil lama: {backup_dir}")
    print(f"{len(strict_gt)} foto, {summary['kb_ingredients']} bahan KB, {len(exact)} anotasi exact, {len(candidates)} kandidat review.")
    print("Exact per kategori:", summary["exact_by_category"])
    print("Kandidat per kategori:", summary["candidates_by_category"])
    print("Sumber kandidat:", summary["candidates_by_source"])
    print("Perubahan dari anotasi lama:", summary["changes_by_type"])


if __name__ == "__main__":
    main()
