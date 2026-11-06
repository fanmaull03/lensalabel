"""Simulate proposed runtime pair blocks against the 40 calibration transcripts."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.seed_knowledge_base_v2 import build_payloads  # noqa: E402
from app.matching.fuzzy_matcher import THRESHOLD, match_token_many  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402

ACTIVE = [
    ("kalium", "kalsium"), ("carbonate", "carbonated"), ("citrate", "nitrate"),
    ("guaran", "guarana"), ("kafein", "kasein"), ("nitrat", "nitrit"),
    ("nitrat", "sitrat"), ("nitrate", "nitrite"), ("baking", "caking"),
    ("sweetened", "sweetener"), ("lembaga", "tembaga"),
    ("jelai", "selai"), ("goat", "oat"),
]
EXPERT_GROUPS = [
    ("malt", "maltodekstrin", "maltitol", "maltosa", "maltol"),
    ("gluten", "glutamat"),
    ("laktosa", "laktat", "laktalbumin"),
]
EXPERT_DISTINCT = [tuple(sorted(pair)) for group in EXPERT_GROUPS for pair in combinations(group, 2)]
ALL = [(pair, "active") for pair in ACTIVE] + [(pair, "expert_distinct") for pair in EXPERT_DISTINCT]


def words(text: str) -> set[str]:
    return {value.casefold() for value in re.findall(r"\w+", text, re.UNICODE)}


def blocked(match) -> list[tuple[tuple[str, str], str]]:
    observed, variant = words(match.matched_window or ""), words(match.matched_variant or "")
    result = []
    for pair, source in ALL:
        left, right = pair
        if (left in observed and right in variant) or (right in observed and left in variant):
            result.append((pair, source))
    return result


def main() -> None:
    with (ROOT / "dataset/ground_truth/transcripts.csv").open(encoding="utf-8-sig", newline="") as stream:
        transcripts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)}
    with (ROOT / "evaluation/splits/calibration_set.csv").open(encoding="utf-8-sig", newline="") as stream:
        photos = [row["filename"] for row in csv.DictReader(stream)]
    payloads = build_payloads()
    kb = [{"ingredient_id": item["id"], "standard_name": item["standard_name"],
           "category": item["category"].value, "name_variant": variant}
          for item in payloads for variant in [item["standard_name"], *item["synonyms"]]]

    hits = []
    current_by_photo, proposed_by_photo = {}, {}
    for filename in photos:
        current, proposed = [], []
        for token in tokenize(extract_composition_section(transcripts[filename])):
            for match in match_token_many(token, kb, threshold=THRESHOLD):
                if not match.matched:
                    continue
                current.append(match)
                pair_hits = blocked(match)
                if not pair_hits:
                    proposed.append(match)
                else:
                    for pair, source in pair_hits:
                        hits.append({"filename": filename, "pair": "/".join(pair), "source": source,
                                     "observed_span": match.matched_window,
                                     "matched_variant": match.matched_variant,
                                     "standard_name": match.standard_name,
                                     "category": match.category, "score": match.score,
                                     "token": token})
        current_by_photo[filename] = {(m.standard_name, m.category) for m in current}
        proposed_by_photo[filename] = {(m.standard_name, m.category) for m in proposed}

    before = Counter(category for values in current_by_photo.values() for _, category in values)
    after = Counter(category for values in proposed_by_photo.values() for _, category in values)
    lost_hindari = []
    for filename in photos:
        lost = current_by_photo[filename] - proposed_by_photo[filename]
        hindari = sorted(name for name, category in lost if category == "hindari")
        if hindari:
            lost_hindari.append({"filename": filename, "lost_hindari": hindari})

    report = {
        "photos": len(photos), "threshold": THRESHOLD,
        "active_pairs": len(ACTIVE), "expert_distinct_pairs": len(EXPERT_DISTINCT),
        "current_prediction_names_by_category": dict(before),
        "after_proposed_block_names_by_category": dict(after),
        "blocked_hit_count": len(hits), "blocked_hits": hits,
        "hindari_lost": lost_hindari, "no_hindari_lost": not lost_hindari,
        "scope": "40 calibration transcript texts only; no OCR, no evaluation split, no metrics",
    }
    out = ROOT / "evaluation/results/kb_v2_phase3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "pair_block_proposal_impact.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out / "pair_block_proposal_impact.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["filename", "pair", "source", "observed_span", "matched_variant", "standard_name", "category", "score", "token"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(hits)
    print(json.dumps({k: v for k, v in report.items() if k != "blocked_hits"}, ensure_ascii=False, indent=2))
    for hit in hits:
        print(json.dumps(hit, ensure_ascii=False))


if __name__ == "__main__":
    main()
