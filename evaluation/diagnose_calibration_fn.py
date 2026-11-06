"""Audit read-only FN kalibrasi dari cache dan fungsi produksi yang tidak diubah."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.matching.fuzzy_matcher import (
    _is_negated_match, _words, find_best_window, load_knowledge_base_from_json, match_token,
)
from app.ocr.reader import sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, tokenize

RESULTS = ROOT / "evaluation/results/colab_v4"
OUTPUT = RESULTS / "fn_diagnostic"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def main():
    kb = load_knowledge_base_from_json(ROOT / "evaluation/kb_snapshot.json")
    variants = defaultdict(list)
    for entry in kb:
        variants[entry["standard_name"]].append(entry)
    ground_truth = json.loads((ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json").read_text(encoding="utf-8"))
    transcripts = {row["filename"]: row for row in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    details = [row for row in read_csv(RESULTS / "grid_detail.csv") if int(row["threshold"]) == 70]
    assert len(details) == 40
    fn_counts = Counter(name for row in details for name in json.loads(row["false_negative"]))
    assert sum(fn_counts.values()) == 168
    OUTPUT.mkdir(parents=True, exist_ok=True)

    @lru_cache(maxsize=None)
    def winner(token):
        return asdict(match_token(token, kb, threshold=70))

    def target_scores(tokens, standard_name, *, include_winner=False):
        scores = []
        for token_index, token in enumerate(tokens):
            best = None
            for entry in variants[standard_name]:
                window, score = find_best_window(token, entry["name_variant"])
                candidate = {"token_index": token_index, "token": token,
                             "window": window, "score": score, "variant": entry["name_variant"],
                             "negated": _is_negated_match(token, window, entry["name_variant"])}
                if best is None or (score, len(_words(window))) > (best["score"], len(_words(best["window"]))):
                    best = candidate
            if best:
                scores.append(best)
        scores.sort(key=lambda item: (-item["score"], -len(_words(item["window"])), item["token_index"]))
        if include_winner:
            for item in scores[:3]:
                item["winner"] = winner(item["token"])
        return scores[:3]

    photos, cases = {}, []
    for index, detail in enumerate(details, 1):
        filename = detail["filename"]
        cache = json.loads((RESULTS / "ocr_cache" / f"{filename}.json").read_text(encoding="utf-8"))
        ordered = sort_reading_order([(entry["bbox"], entry["text"], float(entry["confidence"])) for entry in cache["detections"]])
        raw = "\n".join(text for _, text, _ in ordered)
        composition = extract_composition_section(raw)
        tokens = tokenize(composition)
        original = transcripts[filename]["ground_truth_text"]
        assert original == ground_truth[filename]["ground_truth_text"]
        manual_composition = extract_composition_section(original)
        photo = {"filename": filename, "photo_category": detail["category"],
                 "ground_truth_text": original, "transcript_composition": manual_composition,
                 "ocr_reading_order_text": raw, "ocr_composition_text": composition,
                 "tokens": tokens, "predicted_at_70": json.loads(detail["predicted"]),
                 "ocr_detection_count": len(cache["detections"])}
        photos[filename] = photo
        for name in json.loads(detail["false_negative"]):
            ingredient = next(item for item in ground_truth[filename]["ingredients"] if item["standard_name"] == name)
            cases.append({"filename": filename, "standard_name": name, "category": ingredient["category"],
                          "ground_truth_ingredient": ingredient,
                          "kb_variants": [entry["name_variant"] for entry in variants[name]],
                          "ocr_candidates": target_scores(tokens, name, include_winner=True),
                          "raw_ocr_candidates": target_scores([raw], name),
                          "transcript_candidates": target_scores(tokenize(manual_composition), name)})
        print(f"[{index}/40] {filename}: {detail['fn']} FN", flush=True)
    payload = {"threshold": 70, "total_fn": len(cases), "distinct_standard_names": len(fn_counts),
               "frequency": [{"standard_name": name, "count": count} for name, count in fn_counts.most_common()],
               "photos": photos, "cases": cases,
               "input_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in [RESULTS / "grid_detail.csv", ROOT / "evaluation/kb_snapshot.json",
                                ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json",
                                ROOT / "dataset/ground_truth/transcripts.csv",
                                ROOT / "backend/app/matching/fuzzy_matcher.py",
                                ROOT / "backend/app/tokenizer/tokenizer.py", ROOT / "backend/app/ocr/reader.py"]}}
    (OUTPUT / "evidence.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUTPUT / "all_168_fn.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["filename", "standard_name", "category", "gt_variant", "annotation_source",
                  "best_ocr_score", "ocr_window", "kb_variant", "winner_name", "winner_score", "token",
                  "best_transcript_score", "best_raw_ocr_score"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            best = case["ocr_candidates"][0] if case["ocr_candidates"] else {}
            selected = best.get("winner", {})
            writer.writerow({"filename": case["filename"], "standard_name": case["standard_name"], "category": case["category"],
                             "gt_variant": case["ground_truth_ingredient"]["matched_variant"],
                             "annotation_source": case["ground_truth_ingredient"].get("annotation_source", "strict"),
                             "best_ocr_score": best.get("score"), "ocr_window": best.get("window"),
                             "kb_variant": best.get("variant"), "winner_name": selected.get("standard_name"),
                             "winner_score": selected.get("score"), "token": best.get("token"),
                             "best_transcript_score": case["transcript_candidates"][0]["score"] if case["transcript_candidates"] else None,
                             "best_raw_ocr_score": case["raw_ocr_candidates"][0]["score"] if case["raw_ocr_candidates"] else None})
    print(f"Evidence: {OUTPUT}; {len(cases)} FN", flush=True)


if __name__ == "__main__":
    main()
