"""Regenerate only the blank candidate review workbook from transcripts + KB v2.

This uses exact and lenient annotation helpers only; it does not run OCR,
production matching, classifier, predictions, or metrics.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from evaluation.build_evaluation_annotations import make_workbook, regenerate  # noqa: E402

SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
KB = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
REVIEW = ROOT / "evaluation/ground_truth/evaluation_review.xlsx"
REPORT = ROOT / "evaluation/results/kb_v2_phase3/evaluation_review_regeneration.json"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def flat_kb(payload: dict) -> list[dict]:
    rows = []
    for index, item in enumerate(payload["ingredients"], 1):
        for variant in [item["standard_name"], *item["synonyms"]]:
            rows.append({"ingredient_id": index, "standard_name": item["standard_name"],
                         "category": item["category"], "name_variant": variant})
    return rows


def old_candidate_keys(path: Path) -> set[tuple[str, str, str]]:
    sheet = openpyxl.load_workbook(path, data_only=True).active
    rows = list(sheet.iter_rows(values_only=True))
    fields = [str(value) for value in rows[0]]
    index = {name: fields.index(name) for name in ("filename", "standard_name", "matched_variant")}
    return {(str(row[index["filename"]]), str(row[index["standard_name"]]),
             str(row[index["matched_variant"]])) for row in rows[1:] if row[0]}


def main() -> None:
    split_rows = read_csv(SPLIT)
    transcript_rows = read_csv(TRANSCRIPTS)
    kb_payload = json.loads(KB.read_text(encoding="utf-8-sig"))
    strict, candidates = regenerate(split_rows, transcript_rows, flat_kb(kb_payload))
    if "datar_047.jpeg" not in strict or len(strict) != 160:
        raise ValueError("Evaluation split must contain 160 photos including datar_047.jpeg")
    if any(row.get("keputusan") for row in candidates):
        raise ValueError("New review decisions must remain blank")

    old_keys = old_candidate_keys(REVIEW)
    new_keys = {(row["filename"], row["standard_name"], row["matched_variant"])
                for row in candidates}
    summary = {
        "method": "transcripts_exact_word_boundary_then_lenient_candidates",
        "n_photos": len(strict), "datar_047_in_evaluation": True,
        "candidate_total": len(candidates),
        "candidate_by_category": dict(Counter(row["category"] for row in candidates)),
        "candidate_by_source": dict(Counter(row["sumber"] for row in candidates)),
        "taxonomy_flag_total": sum(row.get("ambigu_taksonomi_tunggu_ahli_gizi") == "ambigu_taksonomi_tunggu_ahli_gizi"
                                    for row in candidates),
        "candidate_new_vs_previous": len(new_keys - old_keys),
        "candidate_missing_vs_previous": len(old_keys - new_keys),
        "new_examples": [dict(filename=f, standard_name=n, matched_variant=v)
                         for f, n, v in sorted(new_keys - old_keys)[:5]],
        "missing_examples": [dict(filename=f, standard_name=n, matched_variant=v)
                            for f, n, v in sorted(old_keys - new_keys)[:5]],
        "decisions": "all blank",
        "kb_sha256": hashlib.sha256(KB.read_bytes()).hexdigest(),
        "transcript_sha256": hashlib.sha256(TRANSCRIPTS.read_bytes()).hexdigest(),
        "split_sha256": hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        "prohibited_inputs_called": ["OCR", "production matcher", "classifier", "predictions", "metrics"],
    }
    wb = make_workbook(candidates, summary)
    wb.save(REVIEW)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
