"""Audit runtime matcher only on the 40 calibration transcripts for pair hits."""
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
PAIRS = [
    ("kalium", "kalsium"),
    ("carbonate", "carbonated"),
    ("citrate", "nitrate"),
    ("guaran", "guarana"),
    ("kafein", "kasein"),
    ("nitrat", "nitrit"),
    ("nitrat", "sitrat"),
    ("nitrate", "nitrite"),
    ("baking", "caking"),
    ("sweetened", "sweetener"),
    ("lembaga", "tembaga"),
    ("jelai", "selai"),
    ("goat", "oat"),
]


def has_word(text: str, word: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.I) is not None


def main() -> None:
    kb_doc = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    kb = []
    for index, entry in enumerate(kb_doc["ingredients"], 1):
        for variant in [entry["standard_name"], *entry.get("synonyms", [])]:
            kb.append({"ingredient_id": index, "standard_name": entry["standard_name"],
                       "category": entry["category"], "name_variant": variant})
    with (ROOT / "dataset/ground_truth/transcripts.csv").open(encoding="utf-8-sig", newline="") as stream:
        transcripts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)}
    with (ROOT / "evaluation/splits/calibration_set.csv").open(encoding="utf-8-sig", newline="") as stream:
        filenames = [row["filename"] for row in csv.DictReader(stream)]

    hits = []
    relevant_token_count = 0
    for filename in filenames:
        for token in tokenize(extract_composition_section(transcripts[filename])):
            if not any(has_word(token, word) for pair in PAIRS for word in pair):
                continue
            relevant_token_count += 1
            for match in match_token_many(token, kb, threshold=75, shared_heads=True):
                if not match.matched:
                    continue
                observed = (match.matched_window or "").casefold()
                variant = (match.matched_variant or "").casefold()
                for left, right in PAIRS:
                    if (has_word(observed, left) and has_word(variant, right)) or (
                        has_word(observed, right) and has_word(variant, left)
                    ):
                        hits.append({
                            "filename": filename,
                            "pair": f"{left}/{right}",
                            "observed_span": match.matched_window,
                            "matched_variant": match.matched_variant,
                            "selected_entry": match.standard_name,
                            "category": match.category,
                            "score": round(match.score, 2),
                            "token": token,
                        })

    with (OUT / "runtime_block_pair_hits_calibration.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["filename", "pair", "observed_span", "matched_variant", "selected_entry", "category", "score", "token"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(hits)
    summary = {
        "kb": "draft_v2",
        "split": "calibration_set.csv",
        "photos": len(filenames),
        "relevant_tokens_scanned": relevant_token_count,
        "pairs_scanned": PAIRS,
        "runtime_forbidden_pair_hits": len(hits),
        "hits": hits,
        "scope": "transcripts only; no 160-photo evaluation split; no OCR",
    }
    (OUT / "runtime_block_pair_hits_calibration.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "hits"}, ensure_ascii=False, indent=2))
    for hit in hits:
        print(json.dumps(hit, ensure_ascii=False))


if __name__ == "__main__":
    main()
