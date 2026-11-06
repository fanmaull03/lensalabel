"""Read-only Phase 2b comparison of archived KB v1 and draft KB v2."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.matching.fuzzy_matcher import match_token_many  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402

OUT = ROOT / "evaluation/results/kb_v2_phase2"
PHRASES = [
    "Tepung Bebas Gluten", "Susu Bebas Laktosa", "Gluten Free", "Tanpa Susu",
    "Susu Kedelai", "Coconut Milk", "Cocoa Butter", "Peanut Butter",
    "Krimer Nabati", "Cream of Tartar", "Susu Skim Bubuk", "Minyak Kelapa Sawit",
]


def flatten(items: list[dict], *, v2: bool = False) -> list[dict]:
    result = []
    for index, item in enumerate(items, 1):
        ingredient_id = index if v2 else item["number"]
        for variant in [item["standard_name"], *item.get("synonyms", [])]:
            result.append({
                "ingredient_id": ingredient_id,
                "standard_name": item["standard_name"],
                "category": item["category"],
                "name_variant": variant,
            })
    return result


def run(text: str, kb: list[dict]) -> list[dict]:
    selected = []
    extracted = extract_composition_section("Komposisi: " + text)
    for token in tokenize(extracted):
        for match in match_token_many(token, kb, threshold=75, shared_heads=True):
            if match.matched:
                selected.append({
                    "name": match.standard_name, "category": match.category,
                    "variant": match.matched_variant, "token": token,
                    "window": match.matched_window, "score": round(match.score, 2),
                    "id": match.ingredient_id,
                })
    return selected


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    old_doc = json.loads((ROOT / "archive/kb_v1_and_gt_before_expert/knowledge_base_gfcf.json").read_text(encoding="utf-8-sig"))
    v2_doc = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    v1 = flatten(old_doc["ingredients"])
    v2 = flatten(v2_doc["ingredients"], v2=True)
    v2_ids = {index: item for index, item in enumerate(v2_doc["ingredients"], 1)}

    context = [{"phrase": phrase, "v1": run(phrase, v1), "v2": run(phrase, v2)} for phrase in PHRASES]
    (OUT / "phase2b_context_v1_v2.json").write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (ROOT / "dataset/ground_truth/transcripts.csv").open(encoding="utf-8-sig", newline="") as stream:
        transcripts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)}
    with (ROOT / "evaluation/splits/calibration_set.csv").open(encoding="utf-8-sig", newline="") as stream:
        calibration = [row["filename"] for row in csv.DictReader(stream)]
    old_mapping = {row["old_no"]: row for row in json.loads((OUT / "old_to_new_mapping.json").read_text(encoding="utf-8"))}

    differences, hindari_losses = [], []
    for filename in calibration:
        old_matches = run(transcripts[filename], v1)
        new_matches = run(transcripts[filename], v2)
        old_pairs = {(m["name"], m["category"]) for m in old_matches}
        new_pairs = {(m["name"], m["category"]) for m in new_matches}
        old_only, new_only = sorted(old_pairs - new_pairs), sorted(new_pairs - old_pairs)
        if old_only or new_only:
            differences.append({
                "filename": filename,
                "v1_only": " || ".join(f"{name} [{category}]" for name, category in old_only),
                "v2_only": " || ".join(f"{name} [{category}]" for name, category in new_only),
                "v1_matches": json.dumps(old_matches, ensure_ascii=False),
                "v2_matches": json.dumps(new_matches, ensure_ascii=False),
            })
        old_hindari_ids = {m["id"] for m in old_matches if m["category"] == "hindari"}
        for old_no in sorted(old_hindari_ids):
            mapping = old_mapping.get(old_no)
            if not mapping or mapping["kategori_baru"] != "hindari":
                continue
            new_id = next((i for i, item in v2_ids.items() if item["new_entry_id"] == mapping["new_entry_id"]), None)
            if new_id is not None and not any(m["id"] == new_id and m["category"] == "hindari" for m in new_matches):
                old_entry = old_doc["ingredients"][old_no - 1]
                hindari_losses.append({
                    "filename": filename, "old_no": old_no,
                    "old_name": old_entry["standard_name"],
                    "new_entry_id": mapping["new_entry_id"],
                    "new_name": v2_ids[new_id]["standard_name"],
                    "old_variant": next((m["variant"] for m in old_matches if m["id"] == old_no), ""),
                })

    write_csv(OUT / "calibration_transcript_match_diff.csv",
              ["filename", "v1_only", "v2_only", "v1_matches", "v2_matches"], differences)
    write_csv(OUT / "calibration_transcript_hindari_losses.csv",
              ["filename", "old_no", "old_name", "new_entry_id", "new_name", "old_variant"], hindari_losses)

    creams = []
    for filename, transcript in transcripts.items():
        if re.search(r"(?<!\w)krimer\s+nabati(?!\w)", transcript, re.IGNORECASE):
            creams.append({"filename": filename, "v1": run(transcript, v1), "v2": run(transcript, v2)})
    (OUT / "krimer_nabati_transcript_matches.json").write_text(json.dumps(creams, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    targets = {
        "cocoa butter": ["cocoa butter", "lemak kakao"],
        "peanut butter": ["peanut butter", "selai kacang tanah"],
        "cream of tartar": ["cream of tartar", "krim tartar"],
    }
    frequency = []
    for phrase, variants in targets.items():
        found = [name for name, text in transcripts.items()
                 if any(re.search(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", text, re.IGNORECASE) for variant in variants)]
        frequency.append({"phrase": phrase, "transcript_photo_count": len(found), "filenames": " | ".join(found)})
    write_csv(OUT / "phase2b_extra_frequency.csv", ["phrase", "transcript_photo_count", "filenames"], frequency)

    summary = {
        "context": context,
        "calibration_photos": len(calibration),
        "calibration_differing_photos": len(differences),
        "calibration_diff_rows": len(differences),
        "hindari_loss_rows": len(hindari_losses),
        "krimer_photo_count": len(creams),
        "krimer_filenames": [row["filename"] for row in creams],
        "frequency": frequency,
    }
    (OUT / "phase2b_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "context": [{
            "phrase": row["phrase"],
            "v1": [(m["name"], m["category"], m["variant"], m["score"]) for m in row["v1"]],
            "v2": [(m["name"], m["category"], m["variant"], m["score"]) for m in row["v2"]],
        } for row in context],
        "calibration_diff_rows": len(differences),
        "hindari_loss_rows": hindari_losses,
        "krimer_count": len(creams),
        "krimer_filenames": [row["filename"] for row in creams],
        "krimer_matches": [{
            "filename": row["filename"],
            "v1": [(m["name"], m["category"], m["variant"], m["score"]) for m in row["v1"] if "krimer" in m["name"].lower() or "susu" in m["name"].lower()],
            "v2": [(m["name"], m["category"], m["variant"], m["score"]) for m in row["v2"] if "krimer" in m["name"].lower() or "susu" in m["name"].lower()],
        } for row in creams],
        "frequency": frequency,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
