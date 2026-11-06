"""Read-only span-level check of the revised creamer gate."""
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
TARGETS = {
    "datar_009.jpeg", "datar_048.jpeg", "datar_051.jpeg", "datar_052.jpeg",
    "datar_094.jpeg", "melengkung_003.jpeg", "melengkung_007.jpeg",
    "melengkung_008.jpeg", "melengkung_009.jpeg", "melengkung_011.jpeg",
    "melengkung_018.jpeg", "melengkung_063.jpeg", "melengkung_065.jpeg",
    "melengkung_066.jpeg",
}
ALLOWED_EXPLICIT_MILK = {
    "datar_094.jpeg", "melengkung_008.jpeg", "melengkung_009.jpeg",
    "melengkung_011.jpeg", "melengkung_018.jpeg", "melengkung_063.jpeg",
    "melengkung_065.jpeg", "melengkung_066.jpeg",
}


def main() -> None:
    kb_doc = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    kb = []
    for index, entry in enumerate(kb_doc["ingredients"], 1):
        for variant in [entry["standard_name"], *entry.get("synonyms", [])]:
            kb.append({
                "ingredient_id": index, "standard_name": entry["standard_name"],
                "category": entry["category"], "name_variant": variant,
            })
    with (ROOT / "dataset/ground_truth/transcripts.csv").open(encoding="utf-8-sig", newline="") as stream:
        transcripts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)}

    rows = []
    for filename in sorted(TARGETS):
        section = extract_composition_section(transcripts[filename])
        phrase_spans = [(m.start(), m.end()) for m in re.finditer(r"(?<!\w)krimer\s+nabati(?!\w)", section, re.I)]
        token_rows = []
        cursor = 0
        for token in tokenize(section):
            start = section.find(token, cursor)
            if start < 0:
                start = section.find(token)
            cursor = start + len(token)
            for match in match_token_many(token, kb, threshold=75, shared_heads=True):
                if not match.matched:
                    continue
                absolute_start = start + (match.span_start or 0)
                absolute_end = start + (match.span_end or 0)
                token_rows.append({
                    "name": match.standard_name, "category": match.category,
                    "variant": match.matched_variant, "window": match.matched_window,
                    "token": token, "local_start": match.span_start,
                    "local_end": match.span_end, "absolute_start": absolute_start,
                    "absolute_end": absolute_end, "score": round(match.score, 2),
                    "entry_index": match.ingredient_id,
                })
        cream = [m for m in token_rows if m["entry_index"] == 26 and "krimer" in m["name"].lower()]
        milk = [m for m in token_rows if m["name"] == "Susu sapi"]
        overlaps = []
        for match in milk:
            for a, b in phrase_spans:
                if max(a, match["absolute_start"]) < min(b, match["absolute_end"]):
                    overlaps.append(match)
        explicit_milk = []
        for match in milk:
            if re.search(r"\bmengandung\b", match["token"], re.I):
                explicit_milk.append(match)
                continue
            prefix = section[max(0, match["absolute_start"] - 240):match["absolute_start"]]
            suffix = section[match["absolute_end"]:min(len(section), match["absolute_end"] + 120)]
            if re.search(r"\bmengandung\b[^)]{0,240}$", prefix, re.I) or re.search(r"^[^)]{0,120}\bmengandung\b", suffix, re.I):
                explicit_milk.append(match)
        specific = []
        for match in milk:
            for more_specific in token_rows:
                if more_specific["token"] != match["token"] or more_specific["name"] == "Susu sapi":
                    continue
                if any(term in more_specific["name"].lower() for term in ("protein susu", "milk protein", "kaseinat", "caseinate")):
                    specific.append(more_specific)
        rows.append({
            "filename": filename,
            "composition_text": section,
            "phrase_spans": phrase_spans,
            "cream_hits": cream,
            "milk_hits": milk,
            "milk_overlap_with_cream": overlaps,
            "explicit_milk_hits": explicit_milk,
            "specific_hits_same_token": specific,
            "passes": (
                len(phrase_spans) == 1 and len(cream) >= 1 and not overlaps
                and (filename in ALLOWED_EXPLICIT_MILK
                     and len(explicit_milk) == len(milk)
                     or filename not in ALLOWED_EXPLICIT_MILK and not milk)
            ),
        })

    (OUT / "krimer_revised_gate_spans.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = []
    for row in rows:
        output.append({
            "filename": row["filename"],
            "krimer_phrase_span_0based_halfopen": " | ".join(f"{a}:{b}" for a, b in row["phrase_spans"]),
            "krimer_span_text": " | ".join(row["composition_text"][a:b] for a, b in row["phrase_spans"]),
            "krimer_entry": " | ".join(f"{m['name']} ({m['category']}) {m['absolute_start']}:{m['absolute_end']}" for m in row["cream_hits"]) or "TIDAK ADA",
            "susu_sapi_span": " | ".join(f"{m['window']} {m['absolute_start']}:{m['absolute_end']}" for m in row["milk_hits"]) or "TIDAK ADA",
            "susu_tidak_tumpang_tindih": "YA" if not row["milk_overlap_with_cream"] else "TIDAK",
            "susu_dari_konteks_mengandung": " | ".join(
                f"{m['window']} {m['absolute_start']}:{m['absolute_end']}" for m in row["explicit_milk_hits"]
            ) or "TIDAK ADA",
            "entri_lebih_spesifik_satu_token": " | ".join(m["name"] for m in row["specific_hits_same_token"]) or "Tidak ada yang terpilih",
            "lulus": "YA" if row["passes"] else "TIDAK",
        })
    with (OUT / "krimer_revised_gate_spans.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    print(json.dumps({
        "photos": len(rows), "all_pass": all(row["passes"] for row in rows),
        "fails": [row["filename"] for row in rows if not row["passes"]],
        "susu_hits": sum(len(row["milk_hits"]) for row in rows),
        "milk_overlap": sum(len(row["milk_overlap_with_cream"]) for row in rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
