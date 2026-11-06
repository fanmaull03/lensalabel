"""Gabungkan keputusan lengkap dari review v4 ke GT final, memakai nama kolom."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
STRICT_GT_PATH = REPO_ROOT / "dataset/ground_truth/calibration_ingredients_gt.json"
REVIEW_XLSX_PATH = REPO_ROOT / "dataset/ground_truth/calibration_review_v4.xlsx"
FINAL_GT_PATH = REPO_ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
KB_PATH = REPO_ROOT / "evaluation/kb_snapshot.json"


def read_reviewed_candidates(path: Path) -> list[dict]:
    source = BytesIO(path.read_bytes())
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        if "kandidat_review" not in workbook.sheetnames:
            raise ValueError("Sheet kandidat_review tidak ditemukan.")
        iterator = workbook["kandidat_review"].iter_rows(values_only=True)
        headers = next(iterator, ())
        nonempty = [header for header in headers if header is not None]
        if len(nonempty) != len(set(nonempty)):
            raise ValueError("Nama kolom review duplikat.")
        required = {"filename", "standard_name", "category", "sumber", "potongan_teks", "keputusan"}
        if required - set(headers):
            raise ValueError(f"Kolom review tidak lengkap: {sorted(required - set(headers))}")
        rows, seen, pending = [], set(), []
        for index, values in enumerate(iterator, 2):
            if not any(value is not None for value in values):
                continue
            row = dict(zip(headers, values))
            if row.get("status_vs_v1") == "HILANG" or row.get("status_vs_v2") == "HILANG":
                continue
            for field in ("filename", "standard_name", "category", "sumber"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"{field} kosong pada baris {index}.")
            if row["category"] not in {"aman", "perhatian", "hindari"}:
                raise ValueError(f"Kategori tidak dikenal pada baris {index}: {row['category']}")
            variant = row.get("matched_variant", row["standard_name"])
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError(f"matched_variant kosong pada baris {index}.")
            row["matched_variant"] = variant
            key = (row["filename"], row["standard_name"], variant)
            if key in seen:
                raise ValueError(f"Kunci kandidat duplikat pada baris {index}: {key}")
            seen.add(key)
            decision = str(row["keputusan"] or "").strip().upper()
            if not decision:
                pending.append(index)
            elif decision not in {"Y", "N"}:
                raise ValueError(f"Keputusan harus Y/N pada baris {index}: {decision}")
            row["keputusan"] = decision
            rows.append(row)
        if pending:
            raise ValueError(f"Merge ditunda: {len(pending)} keputusan aktif belum diisi (baris {pending}).")
        return rows
    finally:
        workbook.close()
        source.close()


def merge_candidates(strict_gt: dict, candidates: list[dict], kb: list[dict]) -> tuple[dict, dict]:
    by_variant = {(entry["standard_name"], entry["name_variant"]): entry for entry in kb}
    final_gt = copy.deepcopy(strict_gt)
    added = 0
    for row in candidates:
        filename = row["filename"]
        if filename not in strict_gt:
            raise ValueError(f"Foto review tidak ada di strict GT: {filename}")
        if row["keputusan"] not in {"Y", "N"}:
            raise ValueError("Merge membutuhkan keputusan lengkap Y/N.")
        if row["keputusan"] == "N":
            continue
        entry = by_variant.get((row["standard_name"], row["matched_variant"]))
        if entry is None or entry["category"] != row["category"]:
            raise ValueError(f"Keputusan Y tidak identik dengan snapshot KB: {filename}, {row['standard_name']}")
        ingredients = final_gt[filename]["ingredients"]
        if any(item["standard_name"] == row["standard_name"] for item in ingredients):
            continue
        ingredients.append({
            "ingredient_id": entry["ingredient_id"], "standard_name": row["standard_name"],
            "category": row["category"], "matched_variant": row["matched_variant"],
            "annotation_source": "review_manual", "review_source": row["sumber"],
        })
        added += 1
    summary = {
        "n_photos": len(final_gt), "approved_total": sum(row["keputusan"] == "Y" for row in candidates),
        "rejected_total": sum(row["keputusan"] == "N" for row in candidates),
        "strict_total": sum(len(info["ingredients"]) for info in strict_gt.values()),
        "manual_added_total": added,
        "final_total": sum(len(info["ingredients"]) for info in final_gt.values()),
        "final_by_category": dict(Counter(ingredient["category"] for info in final_gt.values() for ingredient in info["ingredients"])),
    }
    return final_gt, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-xlsx", "--review", type=Path, default=REVIEW_XLSX_PATH)
    parser.add_argument("--strict-gt", type=Path, default=STRICT_GT_PATH)
    parser.add_argument("--kb-json", type=Path, default=KB_PATH)
    parser.add_argument("--output", type=Path, default=FINAL_GT_PATH)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source_paths = (args.review_xlsx, args.strict_gt, args.kb_json)
    source_hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    strict = json.loads(args.strict_gt.read_text(encoding="utf-8-sig"))
    candidates = read_reviewed_candidates(args.review_xlsx)
    kb = json.loads(args.kb_json.read_text(encoding="utf-8-sig"))
    final_gt, summary = merge_candidates(strict, candidates, kb)
    summary["input_sha256"] = source_hashes
    payload = (json.dumps(final_gt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    summary["final_sha256"] = hashlib.sha256(payload).hexdigest()
    if not args.dry_run:
        if args.output.resolve() in {path.resolve() for path in source_paths}:
            raise ValueError("Output final tidak boleh menimpa file sumber.")
        if args.output.exists() and args.output.read_bytes() != payload:
            raise FileExistsError("GT final berbeda sudah ada; arsipkan dahulu sebelum merge ulang.")
        if args.summary_json and args.summary_json.resolve() in {path.resolve() for path in (*source_paths, args.output)}:
            raise ValueError("Ringkasan tidak boleh menimpa file sumber atau GT final.")
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[str(path.resolve())] for path in source_paths):
            raise ValueError("Input berubah selama merge; jalankan ulang dari input terbaru.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        if args.summary_json:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"GT final: {args.output}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
