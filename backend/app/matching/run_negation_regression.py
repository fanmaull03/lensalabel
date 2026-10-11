"""Read-only before/after verdict regression on the 200 evaluation photos.

Run from backend/:
  python -m app.matching.run_negation_regression

This script runs OCR and both matcher variants against the current knowledge
base. It writes only a report under dataset/debug_output/.
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path

from app.api.routes_identify import decode_image_bytes
from app.classifier.rule_based import classify_product
from app.db.session import SessionLocal
from app.matching.fuzzy_matcher import (
    WEIGHTS,
    THRESHOLD,
    composite_score,
    find_best_window,
    load_knowledge_base,
    match_token,
)
from app.ocr.reader import extract_text
from app.preprocessing.pipeline import preprocess
from app.tokenizer.tokenizer import extract_composition_section, tokenize

ROOT = Path(__file__).resolve().parents[3]
PHOTO_DIRS = (ROOT / "dataset" / "raw_photos" / "datar", ROOT / "dataset" / "raw_photos" / "melengkung")
OUTPUT = ROOT / "dataset" / "debug_output" / "negation_verdict_regression.csv"
FIELDNAMES = [
    "filename",
    "category",
    "verdict_before",
    "verdict_after",
    "changed",
    "removed_matches",
    "added_matches",
]


def old_match_token(token: str, knowledge_base: list[dict]):
    best_entry, best_score, best_window = None, -1.0, None
    for entry in knowledge_base:
        window, score = find_best_window(
            token,
            entry["name_variant"],
            lambda a, b: composite_score(a, b, WEIGHTS),
        )
        if score > best_score:
            best_entry, best_score, best_window = entry, score, window
    if best_entry is None:
        return match_token(token, knowledge_base)
    if best_score < THRESHOLD:
        from app.matching.fuzzy_matcher import MatchResult

        return MatchResult(token=token, matched=False, score=best_score, matched_window=best_window, matched_variant=best_entry["name_variant"])
    from app.matching.fuzzy_matcher import MatchResult

    return MatchResult(
        token=token,
        matched=True,
        score=best_score,
        matched_window=best_window,
        matched_variant=best_entry["name_variant"],
        ingredient_id=best_entry["ingredient_id"],
        standard_name=best_entry["standard_name"],
        category=best_entry["category"],
    )


def classify(raw_text: str, knowledge_base: list[dict], matcher) -> tuple[dict, list]:
    tokens = tokenize(extract_composition_section(raw_text))
    matches = [matcher(token, knowledge_base) for token in tokens]
    return classify_product(matches), matches


def main() -> None:
    photos = [photo for directory in PHOTO_DIRS for photo in sorted(directory.glob("*.jpeg"))]
    with SessionLocal() as session:
        knowledge_base = load_knowledge_base(session)
    if not knowledge_base:
        raise RuntimeError("Knowledge base kosong")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        output.flush()
        os.fsync(output.fileno())

        changed_count = 0
        for index, photo in enumerate(photos, start=1):
            started_at = time.perf_counter()
            raw_text = extract_text(preprocess(decode_image_bytes(photo.read_bytes())))
            before, before_matches = classify(raw_text, knowledge_base, old_match_token)
            after, after_matches = classify(raw_text, knowledge_base, match_token)
            removed_names = {
                before_match.standard_name
                for before_match, after_match in zip(before_matches, after_matches)
                if before_match.matched
                and before_match.standard_name
                and (
                    not after_match.matched
                    or after_match.standard_name != before_match.standard_name
                )
            }
            added_names = {
                after_match.standard_name
                for before_match, after_match in zip(before_matches, after_matches)
                if after_match.matched
                and after_match.standard_name
                and (
                    not before_match.matched
                    or before_match.standard_name != after_match.standard_name
                )
            }
            row = {
                "filename": photo.name,
                "category": photo.parent.name,
                "verdict_before": before["verdict"],
                "verdict_after": after["verdict"],
                "changed": before["verdict"] != after["verdict"],
                "removed_matches": "; ".join(sorted(removed_names)),
                "added_matches": "; ".join(sorted(added_names)),
            }
            writer.writerow(row)
            output.flush()
            os.fsync(output.fileno())
            changed_count += row["changed"]
            elapsed = time.perf_counter() - started_at
            print(f"[{index}/{len(photos)}] {photo.name} selesai ({elapsed:.1f} detik)", flush=True)

    print(f"Berubah: {changed_count}/{len(photos)}")
    print(f"CSV: {OUTPUT}")


if __name__ == "__main__":
    main()
