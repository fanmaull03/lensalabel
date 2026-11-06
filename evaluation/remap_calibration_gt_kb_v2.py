"""Apply the approved calibration GT conflict fixes and map annotations to KB v2.

The source GT is archived before --apply writes a replacement. No OCR,
matcher, classifier, or evaluation code is called here.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.seed_knowledge_base_v2 import build_payloads  # noqa: E402

GT = ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
MAP = ROOT / "evaluation/results/kb_v2_phase2/old_to_new_mapping.json"
KB = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
ARCHIVE = ROOT / "archive/kb_v2_phase3_pre_gt_remap"
REPORT = ROOT / "evaluation/results/kb_v2_phase3/calibration_gt_remap_report.json"
EVALUATION_REVIEW = ROOT / "evaluation/ground_truth/evaluation_review.xlsx"

DROP_SUSU_ROWS = {
    "datar_004.jpeg", "datar_028.jpeg", "datar_029.jpeg",
    "datar_078.jpeg", "melengkung_055.jpeg",
}


def _counts(data: dict) -> dict:
    categories = Counter(
        item["category"] for photo in data.values() for item in photo.get("ingredients", [])
    )
    return {"photos": len(data), "items": sum(categories.values()), "categories": dict(categories)}


def _is_manual(item: dict) -> bool:
    return item.get("annotation_source") == "review_manual"


def remap() -> tuple[dict, dict]:
    source = json.loads(GT.read_text(encoding="utf-8-sig"))
    mapping_rows = json.loads(MAP.read_text(encoding="utf-8-sig"))
    kb_v2 = json.loads(KB.read_text(encoding="utf-8-sig"))
    map_by_old_id: dict[int, list[str]] = defaultdict(list)
    for row in mapping_rows:
        if row.get("old_entry_id") is None:
            continue
        map_by_old_id[int(row["old_entry_id"])].append(row["new_entry_id"])
    entries = {row["new_entry_id"]: row for row in kb_v2["ingredients"]}
    db_ids = {row["new_entry_id"]: int(row["id"]) for row in build_payloads()}
    result = {}
    dropped: list[dict] = []
    unresolved: list[dict] = []
    changed_spans: list[dict] = []
    mapped_rows = 0

    for filename, photo in source.items():
        out_items = []
        for old in photo.get("ingredients", []):
            old_id = int(old["ingredient_id"])
            variant = str(old.get("matched_variant", ""))
            manual = _is_manual(old)

            # Eight explicit expert-approved conflicts.
            drop_reason = None
            if (filename in DROP_SUSU_ROWS and manual
                    and old.get("standard_name") == "Susu sapi" and variant.casefold() == "susu"):
                drop_reason = "approved_conflicting_generic_susu_decision"
            elif filename == "datar_055.jpeg" and manual and old_id == 80:
                drop_reason = "approved_wrong_full_cream_entry_for_skim_milk_span"
            elif filename == "datar_078.jpeg" and manual and variant.casefold() == "beras":
                drop_reason = "approved_overlapping_broad_beras_decision"
            elif filename == "melengkung_090.jpeg" and manual and variant.casefold() == "selulosa":
                drop_reason = "approved_overlapping_cellulose_decision"
            if drop_reason:
                dropped.append({"filename": filename, "old_entry_id": old_id,
                                "standard_name": old.get("standard_name"),
                                "matched_variant": variant, "reason": drop_reason})
                continue

            # The broad Y on “Susu bubuk” and generic “Susu sapi” both overlap
            # the more specific phrase “Padatan Susu Sapi”; retain the specific
            # milk-solids entry already present for melengkung_014.
            if filename == "melengkung_014.jpeg" and (
                    (manual and old_id == 80)
                    or (old_id == 7 and variant.casefold() == "susu sapi")):
                dropped.append({"filename": filename, "old_entry_id": old_id,
                                "standard_name": old.get("standard_name"),
                                "matched_variant": variant,
                                "reason": "split_overlapping_padatan_susu_sapi_to_specific_milk_solids"})
                continue

            # Datar 015: one broad accepted herb/spice span becomes two
            # ingredients whose exact phrases are both present in the transcript.
            if filename == "datar_015.jpeg" and manual and old_id == 139:
                for new_id, span in (("v2-087", "Paprika Oleoresin"),
                                     ("v2-099", "Lada Hitam Bubuk")):
                    entry = entries[new_id]
                    out_items.append({
                        "ingredient_id": db_ids[new_id], "knowledge_base_entry_id": new_id,
                        "standard_name": entry["standard_name"], "category": entry["category"],
                        "matched_variant": span, "annotation_source": "approved_manual_span_split",
                        "review_source": "datar_015_span_split",
                    })
                changed_spans.append({"filename": filename, "from": variant,
                                      "to": ["Paprika Oleoresin", "Lada Hitam Bubuk"],
                                      "mapped_to": ["v2-087", "v2-099"]})
                continue

            # Keep the independently approved “Krimer Bubuk” item, trimming
            # the old KB phrase to the words actually printed on the label.
            if filename == "melengkung_055.jpeg" and manual and old_id == 218:
                variant = "Krimer Bubuk"
                changed_spans.append({"filename": filename, "from": old.get("matched_variant"),
                                      "to": variant, "mapped_to": "v2-194"})

            new_ids = map_by_old_id.get(old_id, [])
            if not new_ids:
                unresolved.append({"filename": filename, "old_entry_id": old_id,
                                   "standard_name": old.get("standard_name"),
                                   "matched_variant": variant, "reason": "no_old_to_new_mapping"})
                continue
            if len(set(new_ids)) > 1:
                if old_id == 89:
                    # Generic margarine with no explicit milk/whey wording is
                    # the “unspecified composition” branch approved by expert.
                    around = photo.get("ground_truth_text", "").casefold()
                    explicit = "whey" in around or "mengandung susu" in around
                    new_id = "v2-028a" if explicit else "v2-028b"
                elif old_id == 251:
                    text = photo.get("ground_truth_text", "").casefold()
                    new_id = "v2-234a" if "ekstrak licorice" in text else "v2-234b"
                else:
                    unresolved.append({"filename": filename, "old_entry_id": old_id,
                                       "standard_name": old.get("standard_name"),
                                       "matched_variant": variant,
                                       "reason": "split_mapping_requires_case_review",
                                       "candidate_new_ids": sorted(set(new_ids))})
                    continue
            else:
                new_id = new_ids[0]

            entry = entries[new_id]
            # Specific milk powder outranks the older broad “Susu bubuk” row
            # when the transcript explicitly says “Susu Bubuk Skim”.
            if (old_id == 80 and re.search(r"(?<!\w)susu\s+skim\s+bubuk(?!\w)|(?<!\w)susu\s+bubuk\s+skim(?!\w)",
                                            photo.get("ground_truth_text", ""), re.IGNORECASE)):
                new_id = "v2-193"
                entry = entries[new_id]
            new_item = {key: value for key, value in old.items()
                        if key not in {"ingredient_id", "standard_name", "category"}}
            new_item.update({
                "ingredient_id": db_ids[new_id], "knowledge_base_entry_id": new_id,
                "standard_name": entry["standard_name"], "category": entry["category"],
                "matched_variant": variant,
            })
            if entry["standard_name"] != old.get("standard_name") or entry["category"] != old.get("category"):
                new_item["mapped_from"] = {"ingredient_id": old_id,
                                             "standard_name": old.get("standard_name"),
                                             "category": old.get("category")}
            out_items.append(new_item)
            mapped_rows += 1

        # “Padatan susu” is only accepted when those words occur in this
        # transcript; melengkung_055 does not contain that phrase.
        text = photo.get("ground_truth_text", "").casefold()
        if filename == "melengkung_055.jpeg" and "padatan susu" not in text:
            out_items = [item for item in out_items
                         if not (item.get("knowledge_base_entry_id") == "v2-194"
                                 and item.get("matched_variant", "").casefold() == "padatan susu")]

        # Several legacy entries merge to one KB v2 entity. Keep one row per
        # mapped ingredient per photo, preserving a real/most-specific span.
        deduped = {}
        for item in out_items:
            key = item["knowledge_base_entry_id"]
            if key not in deduped or len(item.get("matched_variant", "")) > len(deduped[key].get("matched_variant", "")):
                deduped[key] = item
        photo_copy = dict(photo)
        photo_copy["ingredients"] = sorted(deduped.values(), key=lambda x: (x["category"], x["standard_name"].casefold()))
        result[filename] = photo_copy

    report = {
        "source": str(GT.relative_to(ROOT)), "mapping": str(MAP.relative_to(ROOT)),
        "before": _counts(source), "after": _counts(result),
        "dropped_decisions": dropped, "dropped_count": len(dropped),
        "changed_or_split_spans": changed_spans,
        "unresolved": unresolved, "unresolved_count": len(unresolved),
        "mapped_rows_before_deduplication": mapped_rows,
        "deduplication_note": "Merged old entries are represented once per photo using KB v2 entry ID.",
        "reference_count_stated_by_user": {"items": 221, "hindari": 36, "perhatian": 112, "aman": 73},
    }
    return result, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Archive source and write remapped GT")
    args = parser.parse_args()
    result, report = remap()
    if args.apply:
        if ARCHIVE.exists():
            raise SystemExit(f"Archive already exists; refusing overwrite: {ARCHIVE}")
        ARCHIVE.mkdir(parents=True)
        shutil.copy2(GT, ARCHIVE / GT.name)
        if EVALUATION_REVIEW.exists():
            shutil.copy2(EVALUATION_REVIEW, ARCHIVE / EVALUATION_REVIEW.name)
        report["archived_source"] = str((ARCHIVE / GT.name).relative_to(ROOT))
        if (ARCHIVE / EVALUATION_REVIEW.name).exists():
            report["archived_evaluation_review"] = str((ARCHIVE / EVALUATION_REVIEW.name).relative_to(ROOT))
        GT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
