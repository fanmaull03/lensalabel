"""Read-only calibration transcript specificity audit and proposal simulation."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.seed_knowledge_base_v2 import build_payloads  # noqa: E402
from app.matching.fuzzy_matcher import THRESHOLD, match_token_many  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402

SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
OUT = ROOT / "evaluation/results/kb_v2_phase3"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def phrase_re(phrase: str):
    words = re.findall(r"\w+", phrase, flags=re.UNICODE)
    return re.compile(r"(?<!\w)" + r"[^\w]+".join(map(re.escape, words)) + r"(?!\w)", re.IGNORECASE)


def main() -> None:
    transcripts = {row["filename"]: row for row in read_csv(TRANSCRIPTS)}
    split = read_csv(SPLIT)
    payloads = build_payloads()
    entry_by_pk = {row["id"]: row for row in payloads}
    kb = [{"ingredient_id": row["id"], "standard_name": row["standard_name"],
           "category": row["category"].value, "name_variant": variant}
          for row in payloads for variant in [row["standard_name"], *row["synonyms"]]]
    variants_by_entry: dict[int, list[str]] = defaultdict(list)
    for row in kb:
        variants_by_entry[row["ingredient_id"]].append(row["name_variant"])

    changes = []
    pair_counts = Counter()
    before_by_category = Counter()
    after_by_category = Counter()
    before_photo = {}
    after_photo = {}
    removed_hindari = []
    for split_row in split:
        filename = split_row["filename"]
        text = extract_composition_section(transcripts[filename]["ground_truth_text"])
        original, filtered = [], []
        for token in tokenize(text):
            matches = [m for m in match_token_many(token, kb, threshold=THRESHOLD) if m.matched]
            for match in matches:
                original.append(match)
                longer = []
                for other in kb:
                    if other["ingredient_id"] == match.ingredient_id:
                        continue
                    variant_words = re.findall(r"\w+", other["name_variant"])
                    matched_words = re.findall(r"\w+", match.matched_variant or "")
                    if len(variant_words) <= len(matched_words):
                        continue
                    for occurrence in phrase_re(other["name_variant"]).finditer(token):
                        if (match.span_start is not None and match.span_end is not None
                                and occurrence.start() <= match.span_start
                                and match.span_end <= occurrence.end()):
                            longer.append((other, occurrence.group(), occurrence.start(), occurrence.end()))
                if longer:
                    other, long_text, left, right = max(
                        longer, key=lambda value: (value[3] - value[2], len(value[0]["name_variant"]))
                    )
                    key = (entry_by_pk[match.ingredient_id]["new_entry_id"],
                           other["standard_name"], match.matched_variant or "", other["name_variant"])
                    pair_counts[key] += 1
                    changes.append({
                        "filename": filename, "token": token,
                        "generic_entry_id": entry_by_pk[match.ingredient_id]["new_entry_id"],
                        "generic_name": match.standard_name, "generic_category": match.category,
                        "generic_variant": match.matched_variant, "generic_span": match.matched_window,
                        "specific_name": other["standard_name"], "specific_category": other["category"],
                        "specific_variant": other["name_variant"], "specific_span": long_text,
                        "score": match.score,
                    })
                    continue
                filtered.append(match)

        before_photo[filename] = {(m.standard_name, m.category) for m in original}
        after_photo[filename] = {(m.standard_name, m.category) for m in filtered}
        for _, category in before_photo[filename]:
            before_by_category[category] += 1
        for _, category in after_photo[filename]:
            after_by_category[category] += 1
        lost_hindari = before_photo[filename] - after_photo[filename]
        if any(category == "hindari" for _, category in lost_hindari):
            removed_hindari.append({"filename": filename, "lost": sorted(lost_hindari)})

    pair_rows = []
    for (generic_id, specific_name, generic_variant, specific_variant), count in pair_counts.most_common():
        sample = next(row for row in changes if row["generic_entry_id"] == generic_id
                      and row["specific_name"] == specific_name
                      and row["generic_variant"] == generic_variant
                      and row["specific_variant"] == specific_variant)
        pair_rows.append({"generic_entry_id": generic_id, "generic_name": sample["generic_name"],
                          "generic_category": sample["generic_category"],
                          "generic_variant": generic_variant, "specific_name": specific_name,
                          "specific_category": sample["specific_category"],
                          "specific_variant": specific_variant, "photos": sorted({
                              row["filename"] for row in changes
                              if row["generic_entry_id"] == generic_id and row["specific_name"] == specific_name
                              and row["generic_variant"] == generic_variant
                              and row["specific_variant"] == specific_variant}),
                          "match_occurrences": count})
    entries_by_new_id = {row["new_entry_id"]: row for row in payloads}
    focused_pairs = [
        ("v2-015", "Susu", "v2-193", "Susu skim bubuk"),
        ("v2-016", "Susu bubuk", "v2-193", "Susu skim bubuk"),
        ("v2-141", "Minyak kelapa", "v2-159", "Minyak kelapa sawit"),
        ("v2-015", "Susu", "v2-new-012", "Konsentrat protein susu"),
    ]
    focused_rows = []
    for generic_id, generic_variant, specific_id, specific_variant in focused_pairs:
        specific_entry = entries_by_new_id[specific_id]
        occurrence_photos = set()
        occurrence_count = generic_selected = specific_selected = 0
        selected_by_photo = defaultdict(list)
        pattern = phrase_re(specific_variant)
        for split_row in split:
            filename = split_row["filename"]
            text = extract_composition_section(transcripts[filename]["ground_truth_text"])
            for token in tokenize(text):
                occurrences = list(pattern.finditer(token))
                if not occurrences:
                    continue
                matches = [m for m in match_token_many(token, kb, threshold=THRESHOLD) if m.matched]
                for occurrence in occurrences:
                    occurrence_count += 1
                    occurrence_photos.add(filename)
                    selected = [m for m in matches if m.span_start is not None and m.span_end is not None
                                and occurrence.start() <= m.span_start and m.span_end <= occurrence.end()]
                    if any(m.ingredient_id == entries_by_new_id[generic_id]["id"] for m in selected):
                        generic_selected += 1
                    if any(m.ingredient_id == specific_entry["id"] for m in selected):
                        specific_selected += 1
                    selected_by_photo[filename].extend(
                        {"standard_name": m.standard_name, "matched_variant": m.matched_variant,
                         "span": m.matched_window, "category": m.category, "score": m.score}
                        for m in selected)
        focused_rows.append({
            "generic_entry_id": generic_id, "generic_name": entries_by_new_id[generic_id]["standard_name"],
            "generic_category": entries_by_new_id[generic_id]["category"].value,
            "generic_variant": generic_variant, "specific_entry_id": specific_id,
            "specific_name": specific_entry["standard_name"],
            "specific_category": specific_entry["category"].value,
            "specific_variant": specific_variant, "phrase_occurrences": occurrence_count,
            "photos": sorted(occurrence_photos), "generic_selected_count": generic_selected,
            "specific_selected_count": specific_selected,
            "selected_results": dict(selected_by_photo),
        })
    report = {
        "photos": len(split), "threshold": THRESHOLD,
        "current_match_count_by_category": dict(before_by_category),
        "after_span_specificity_filter_by_category": dict(after_by_category),
        "removed_match_count": len(changes), "removed_hindari": removed_hindari,
        "no_hindari_lost": not removed_hindari,
        "pair_count": len(pair_rows), "specificity_pairs": pair_rows,
        "focused_superset_checks": focused_rows,
        "specificity_examples": changes,
        "method_note": "Runs current matcher on the 40 transcript texts only, then simulates dropping a selected match when its exact span is contained by a longer KB v2 variant from another entry. No photos/OCR and no 160 split.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "specificity_audit_calibration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "specificity_audit_calibration.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["filename", "generic_name", "generic_category", "generic_variant", "generic_span",
                  "specific_name", "specific_category", "specific_variant", "specific_span", "score", "token"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(changes)
    print(json.dumps({k: v for k, v in report.items() if k != "specificity_examples"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
