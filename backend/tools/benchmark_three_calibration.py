"""Measure one local OCR pass and both matchers on three calibration photos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.api.routes_identify import decode_image_bytes
from app.classifier.rule_based import classify_product
from app.matching import fuzzy_matcher, fuzzy_matcher_optimized
from app.ocr.reader import extract_text, get_reader
from app.preprocessing.pipeline import preprocess
from app.tokenizer.tokenizer import extract_composition_section, tokenize

SAMPLES = ("melengkung_076.jpeg", "datar_095.jpeg", "datar_015.jpeg")
WEIGHTS = {"levenshtein": 1 / 3, "jaro_winkler": 1 / 3, "ngram": 1 / 3}


def elapsed(call):
    start = perf_counter()
    result = call()
    return result, perf_counter() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads((BACKEND / "app/db/knowledge_base_v2_deploy.json").read_text(encoding="utf-8"))
    kb = [{"ingredient_id": row["id"], "standard_name": row["standard_name"],
           "category": row["category"], "name_variant": variant}
          for row in source["ingredients"]
          for variant in [row["standard_name"], *row["synonyms"]]]
    _, model_seconds = elapsed(get_reader)
    rows = []
    for filename in SAMPLES:
        condition = filename.split("_", 1)[0]
        path = args.research_root / "dataset/raw_photos" / condition / filename
        image, decode_seconds = elapsed(lambda: decode_image_bytes(path.read_bytes()))
        prepared, preprocess_seconds = elapsed(lambda: preprocess(image))
        raw, ocr_seconds = elapsed(lambda: extract_text(prepared, max_width=1500))
        tokens, extraction_seconds = elapsed(lambda: tokenize(extract_composition_section(raw)))
        times = {}
        signatures = {}
        for label, module in (("frozen", fuzzy_matcher), ("optimized", fuzzy_matcher_optimized)):
            def run_matcher():
                matches = [match for token in tokens for match in module.match_token_many(
                    token, kb, weights=WEIGHTS, threshold=75, shared_heads=True,
                    secondary_min_score=None, secondary_full_coverage=False,
                    length_penalty_exponent=0.8)]
                return matches, classify_product(matches)
            (matches, classified), seconds = elapsed(run_matcher)
            times[label] = seconds
            signatures[label] = ([m.__dict__ for m in matches], classified)
        if signatures["frozen"] != signatures["optimized"]:
            raise RuntimeError(f"Prediksi tidak identik: {filename}")
        base = decode_seconds + preprocess_seconds + ocr_seconds + extraction_seconds
        row = {"filename": filename, "condition": condition,
               "decode_seconds": decode_seconds, "preprocess_seconds": preprocess_seconds,
               "ocr_seconds": ocr_seconds, "extract_tokenize_seconds": extraction_seconds,
               "frozen_matcher_seconds": times["frozen"],
               "optimized_matcher_seconds": times["optimized"],
               "frozen_total_seconds": base + times["frozen"],
               "optimized_total_seconds": base + times["optimized"]}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {"model_load_seconds": model_seconds, "photos": rows,
              "first_photo_cold_total_frozen": model_seconds + rows[0]["frozen_total_seconds"],
              "first_photo_cold_total_optimized": model_seconds + rows[0]["optimized_total_seconds"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
