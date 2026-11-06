"""Build a KB v2-canonical evaluation GT after expert mapping review is complete.

The source GT is never overwritten. Every output item uses a KB v2 canonical
standard_name and the corresponding KB v2 category. Three split mappings are
blocked until the expert-review workbook contains a valid decision.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SOURCE_GT = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
KB_PATH = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
SPLIT_PATH = ROOT / "evaluation/splits/evaluation_set.csv"
REVIEW_PATH = ROOT / "evaluation/results/gt_v2_alignment/validasi_pemetaan_gt_ke_kb_v2.xlsx"
OUT_DIR = ROOT / "evaluation/results/gt_v2_alignment"
OUTPUT_GT = ROOT / "evaluation/ground_truth/evaluation_gt_kb_v2_final.json"
REPORT_PATH = OUT_DIR / "evaluation_gt_kb_v2_alignment_report.json"

DIRECT_NAME_MAPPINGS = {
    "Gula pasir murni": "v2-147",
    "Sukrosa": "v2-147",
    "Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum": "v2-147",
    "Natrium karboksimetil selulosa (Na-CMC)": "v2-206",
    "Metil selulosa / Karboksi metil selulosa": "v2-206",
}

AMBIGUOUS_MAPPING_KEYS = {
    ("datar_022.jpeg", "Margarin (mengandung whey/susu)"),
    ("datar_027.jpeg", "Margarin (mengandung whey/susu)"),
    ("melengkung_096.jpeg", "Licorice"),
}

# Expert decision on melengkung_096.jpeg: the label only says "PERISA ALAMI
# LICORICE", which supports neither the extract nor the candy KB v2 branch.
# The annotation is excluded from ingredient scoring rather than forced into
# an unsupported entry; the photo keeps its own product verdict.
EXCLUDED_ANNOTATIONS = {
    ("melengkung_096.jpeg", "Licorice"): {
        "decision": "TIDAK_DAPAT_DITETAPKAN",
        "reason": "Permukaan label hanya menyebut PERISA ALAMI LICORICE; tidak mendukung ekstrak licorice maupun permen licorice pada KB v2.",
        "approved_by": "validasi_ahli",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_kb(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = document.get("ingredients", document)
    by_id = {str(entry["new_entry_id"]): entry for entry in entries}
    by_name = {str(entry["standard_name"]): entry for entry in entries}
    return by_id, by_name


def read_review(path: Path) -> dict[tuple[str, str], str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "keputusan_ahli" not in workbook.sheetnames:
            raise ValueError("Sheet keputusan_ahli tidak ditemukan.")
        sheet = workbook["keputusan_ahli"]
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        required = {"nama_file", "nama_gt_lama", "kandidat_A", "kandidat_B", "keputusan_final"}
        missing = required - set(headers)
        if missing:
            raise ValueError(f"Kolom review tidak lengkap: {sorted(missing)}")
        rows = [dict(zip(headers, values)) for values in sheet.iter_rows(min_row=2, values_only=True)
                if any(value is not None for value in values)]
    finally:
        workbook.close()

    decisions: dict[tuple[str, str], str] = {}
    for row in rows:
        filename = str(row["nama_file"] or "")
        old_name = str(row["nama_gt_lama"] or "")
        decision = str(row["keputusan_final"] or "").strip()
        key = (filename, old_name)
        if not decision:
            raise ValueError(f"Keputusan ahli kosong untuk {filename}: {old_name}")
        if decision == "TIDAK_DAPAT_DITETAPKAN":
            if key not in EXCLUDED_ANNOTATIONS:
                raise ValueError(f"Ahli menyatakan {filename}: {old_name} tidak dapat ditetapkan, tetapi tidak ada keputusan lanjutan yang disetujui.")
            decisions[key] = decision
            continue
        allowed = {str(row["kandidat_A"]), str(row["kandidat_B"])}
        if decision not in allowed:
            raise ValueError(f"Keputusan {decision!r} tidak sesuai kandidat {sorted(allowed)} untuk {filename}: {old_name}")
        if key in decisions:
            raise ValueError(f"Keputusan duplikat untuk {filename}: {old_name}")
        decisions[key] = decision

    missing = AMBIGUOUS_MAPPING_KEYS - set(decisions)
    unexpected = set(decisions) - AMBIGUOUS_MAPPING_KEYS
    if missing or unexpected:
        raise ValueError(f"Cakupan review ahli tidak sesuai; missing={sorted(missing)}, unexpected={sorted(unexpected)}")
    return decisions


def allowed_filenames(split_path: Path) -> set[str]:
    with split_path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["filename"] for row in csv.DictReader(stream)}


def canonical_id(entry: dict) -> int:
    old_ids = [int(value) for value in entry.get("old_entry_ids", [])]
    if old_ids:
        return min(old_ids)
    return int(hashlib.sha256(str(entry["new_entry_id"]).encode("utf-8")).hexdigest()[:8], 16)


def build_aligned_gt(source: dict, kb_by_id: dict[str, dict], kb_by_name: dict[str, dict], decisions: dict[tuple[str, str], str]) -> tuple[dict, dict]:
    output: dict = {}
    mapping_events: list[dict] = []
    excluded_events: list[dict] = []
    category_changes: Counter[tuple[str, str]] = Counter()

    for filename, record in source.items():
        aligned_items = []
        for item in record.get("ingredients", []):
            old_name = str(item["standard_name"])
            old_category = str(item["category"]).casefold()
            review_key = (filename, old_name)
            if review_key in EXCLUDED_ANNOTATIONS:
                excluded_events.append({
                    "filename": filename,
                    "old_standard_name": old_name,
                    "old_category": old_category,
                    "matched_variant": item.get("matched_variant"),
                    **EXCLUDED_ANNOTATIONS[review_key],
                })
                continue
            mapping_source = "canonical_sudah_ada"
            if old_name in kb_by_name:
                entry = kb_by_name[old_name]
            elif old_name in DIRECT_NAME_MAPPINGS:
                entry = kb_by_id[DIRECT_NAME_MAPPINGS[old_name]]
                mapping_source = "pemetaan_alias_tidak_ambigu"
            else:
                if review_key not in decisions:
                    raise ValueError(f"Tidak ada pemetaan KB v2 untuk {filename}: {old_name}")
                entry = kb_by_id[decisions[review_key]]
                mapping_source = "keputusan_ahli"

            new_category = str(entry["category"]).casefold()
            aligned = {key: value for key, value in item.items() if key not in {"ingredient_id", "standard_name", "category"}}
            aligned.update({
                "ingredient_id": canonical_id(entry),
                "knowledge_base_entry_id": entry["new_entry_id"],
                "standard_name": entry["standard_name"],
                "category": new_category,
            })
            if old_name != entry["standard_name"] or old_category != new_category:
                aligned["aligned_from"] = {
                    "standard_name": old_name,
                    "category": old_category,
                    "mapping_source": mapping_source,
                }
                mapping_events.append({
                    "filename": filename,
                    "old_standard_name": old_name,
                    "new_entry_id": entry["new_entry_id"],
                    "new_standard_name": entry["standard_name"],
                    "old_category": old_category,
                    "new_category": new_category,
                    "mapping_source": mapping_source,
                })
            if old_category != new_category:
                category_changes[(old_category, new_category)] += 1
            aligned_items.append(aligned)

        deduped: dict[str, dict] = {}
        for item in aligned_items:
            key = item["knowledge_base_entry_id"]
            current = deduped.get(key)
            if current is None or len(str(item.get("matched_variant") or "")) > len(str(current.get("matched_variant") or "")):
                deduped[key] = item
        output[filename] = {**record, "ingredients": sorted(
            deduped.values(), key=lambda row: (row["category"], row["standard_name"].casefold())
        )}

    report = {
        "mapping_events": mapping_events,
        "mapping_count": len(mapping_events),
        "excluded_annotations": excluded_events,
        "excluded_count": len(excluded_events),
        "category_change_counts": {
            f"{old}->{new}": count for (old, new), count in sorted(category_changes.items())
        },
        "photos": len(output),
        "items": sum(len(record.get("ingredients", [])) for record in output.values()),
        "categories": dict(Counter(item["category"] for record in output.values() for item in record.get("ingredients", []))),
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the aligned GT and alignment report.")
    parser.add_argument("--output", type=Path, default=OUTPUT_GT)
    args = parser.parse_args()

    source = json.loads(SOURCE_GT.read_text(encoding="utf-8-sig"))
    expected = allowed_filenames(SPLIT_PATH)
    if set(source) != expected:
        raise SystemExit("GT sumber tidak mencakup tepat 160 foto pada evaluation_set.csv.")
    decisions = read_review(REVIEW_PATH)
    kb_by_id, kb_by_name = load_kb(KB_PATH)
    aligned, report = build_aligned_gt(source, kb_by_id, kb_by_name, decisions)
    missing = sorted({item["standard_name"] for record in aligned.values() for item in record.get("ingredients", [])} - set(kb_by_name))
    if missing:
        raise SystemExit("GT hasil masih memiliki nama di luar KB v2: " + ", ".join(missing))

    result = {
        **report,
        "source_gt": str(SOURCE_GT.relative_to(ROOT)).replace("\\", "/"),
        "source_gt_sha256": sha256(SOURCE_GT),
        "kb_v2": str(KB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "kb_v2_sha256": sha256(KB_PATH),
        "expert_review": str(REVIEW_PATH.relative_to(ROOT)).replace("\\", "/"),
        "expert_decisions": [
            {"filename": filename, "nama_gt_lama": old_name, "decision": decision}
            for (filename, old_name), decision in sorted(decisions.items())
        ],
        "output": str(args.output.relative_to(ROOT)).replace("\\", "/"),
        "output_written": False,
    }
    if args.apply:
        if args.output.exists():
            raise SystemExit(f"Refusing to overwrite existing aligned GT: {args.output}")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(aligned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["output_sha256"] = sha256(args.output)
        result["output_written"] = True
        result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
