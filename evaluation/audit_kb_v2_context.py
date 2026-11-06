"""Run synthetic read-only context cases against the Phase 2 KB draft."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.matching.fuzzy_matcher import THRESHOLD, match_token_many  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, tokenize  # noqa: E402


OUT = ROOT / "evaluation/results/kb_v2_phase2"
SCENARIOS = [
    ("Tepung Bebas Gluten", [], ["v2-new-001", "v2-149"],
     "Gluten tidak menjadi Hindari; tanpa jenis tepung yang disebut, Tepung beras juga tidak boleh ditambahkan"),
    ("Susu Bebas Laktosa", ["v2-new-009"], ["v2-015"], "Susu bebas laktosa tetap Hindari sebagai produk susu"),
    ("Gluten Free", [], ["v2-new-001"], "Gluten tidak menjadi Hindari karena dinegasikan"),
    ("Tanpa Susu", [], ["v2-015"], "Susu sapi tidak menjadi Hindari karena dinegasikan"),
    ("Susu Kedelai", ["v2-145"], ["v2-015"], "Susu kedelai Aman tanpa Susu sapi"),
    ("Coconut Milk", ["v2-142"], ["v2-015"], "Susu kelapa Aman tanpa Susu sapi"),
    ("Cocoa Butter", ["v2-new-020"], ["v2-019"], "Cocoa butter Aman tanpa mentega hewani"),
    ("Peanut Butter", ["v2-new-021"], ["v2-019"], "Peanut butter Aman tanpa mentega hewani"),
    ("Krimer Nabati", ["v2-029"], ["v2-015"], "Krimer nabati Perlu Perhatian tanpa Susu sapi"),
    ("Cream of Tartar", ["v2-new-022"], ["v2-020"], "Cream of tartar Aman tanpa krim susu"),
    ("Susu Skim Bubuk", ["v2-193"], ["v2-015"], "Susu skim bubuk Hindari dengan entri spesifik"),
    ("Minyak Kelapa Sawit", ["v2-159"], ["v2-141"], "Minyak kelapa sawit Aman tanpa minyak kelapa"),
]


def load_kb() -> tuple[list[dict], dict[int, str], dict[str, dict]]:
    payload = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    items = payload["ingredients"]
    by_id = {item["new_entry_id"]: item for item in items}
    kb, numeric = [], {}
    for number, item in enumerate(items, 1):
        numeric[number] = item["new_entry_id"]
        for variant in [item["standard_name"], *item["synonyms"]]:
            kb.append({"ingredient_id": number, "standard_name": item["standard_name"],
                       "category": item["category"], "name_variant": variant})
    return kb, numeric, by_id


def evaluate(phrase: str, must_have: list[str], must_not_have: list[str], expected: str,
             kb: list[dict], numeric: dict[int, str], by_id: dict[str, dict]) -> dict:
    text = extract_composition_section("Komposisi: " + phrase)
    tokens = tokenize(text)
    matches = [match for token in tokens for match in match_token_many(token, kb, threshold=THRESHOLD)
               if match.matched]
    actual = [{"new_entry_id": numeric[match.ingredient_id], "standard_name": match.standard_name,
               "category": match.category, "matched_window": match.matched_window,
               "matched_variant": match.matched_variant, "score": match.score}
              for match in matches]
    got = {entry["new_entry_id"] for entry in actual}
    checks = {"expected_present": all(value in got for value in must_have),
              "forbidden_absent": all(value not in got for value in must_not_have)}
    return {"input": phrase, "extracted": text, "tokens": tokens,
            "threshold_default": THRESHOLD, "expected_description": expected,
            "must_have": [{"new_entry_id": i, "name": by_id[i]["standard_name"],
                           "category": by_id[i]["category"]} for i in must_have],
            "must_not_have": [{"new_entry_id": i, "name": by_id[i]["standard_name"],
                               "category": by_id[i]["category"]} for i in must_not_have],
            "actual": actual, "checks": checks, "pass": all(checks.values())}


def main() -> None:
    kb, numeric, by_id = load_kb()
    results = [evaluate(phrase, yes, no, expected, kb, numeric, by_id)
               for phrase, yes, no, expected in SCENARIOS]
    (OUT / "context_regression.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "context_regression.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["input", "expected_description", "actual_names",
                                                       "actual_categories", "scores", "pass"])
        writer.writeheader()
        for row in results:
            writer.writerow({"input": row["input"], "expected_description": row["expected_description"],
                             "actual_names": " | ".join(x["standard_name"] for x in row["actual"]),
                             "actual_categories": " | ".join(x["category"] for x in row["actual"]),
                             "scores": " | ".join(str(x["score"]) for x in row["actual"]),
                             "pass": row["pass"]})
    print(json.dumps({"cases": len(results), "passed": sum(row["pass"] for row in results),
                      "failed": [row["input"] for row in results if not row["pass"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
