"""Script to run targeted regression and print full detailed comparison for each photo."""

import json
from pathlib import Path
import cv2
import easyocr
import numpy as np

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")

import sys
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, tokenize

def sort_reading_order_v1(results: list) -> list[tuple[list, str, float]]:
    """Original reading order sorting."""
    if not results:
        return []

    detections = []
    heights = []
    for bbox, text, confidence in results:
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        height = max(ys) - min(ys)
        detections.append((bbox, text, confidence, sum(ys) / len(ys), min(xs)))
        heights.append(height)

    tolerance = max(float(np.mean(heights)) * 0.5, 1.0)
    lines = []
    for detection in sorted(detections, key=lambda item: item[3]):
        line = min(lines, key=lambda item: abs(item["center_y"] - detection[3]), default=None)
        if line is None or abs(line["center_y"] - detection[3]) > tolerance:
            lines.append({"center_y": detection[3], "items": [detection]})
        else:
            line["items"].append(detection)
            line["center_y"] = float(np.mean([item[3] for item in line["items"]]))

    ordered = []
    for line in sorted(lines, key=lambda item: item["center_y"]):
        ordered.extend(sorted(line["items"], key=lambda item: item[4]))
    return [(bbox, text, confidence) for bbox, text, confidence, _, _ in ordered]

def main():
    reader = easyocr.Reader(["id", "en"], gpu=False)

    test_photos = [
        # Group 1: Kasus bermasalah (multi-kolom / Nutrition panel kiri)
        ("melengkung_005.jpeg", "melengkung"),
        ("datar_002.jpeg", "datar"),
        # Group 2: Kasus normal / single-column terverifikasi bagus
        ("datar_001.jpeg", "datar"),
        ("datar_003.jpeg", "datar"),
        ("datar_004.jpeg", "datar"),
        ("datar_005.jpeg", "datar"),
        ("melengkung_001.jpeg", "melengkung"),
        ("melengkung_002.jpeg", "melengkung"),
        ("melengkung_003.jpeg", "melengkung"),
        ("melengkung_004.jpeg", "melengkung"),
    ]

    all_data = []
    for photo_name, cat in test_photos:
        photo_path = REPO_ROOT / "dataset" / "raw_photos" / cat / photo_name
        img = cv2.imread(str(photo_path))
        prep = preprocess(img)
        ocr_img = _downscale(prep, MAX_OCR_WIDTH)
        raw_results = reader.readtext(ocr_img, detail=1)

        ordered_v1 = sort_reading_order_v1(raw_results)
        text_v1 = "\n".join(t for _, t, _ in ordered_v1)
        comp_v1 = extract_composition_section(text_v1)
        tokens_v1 = tokenize(comp_v1)

        ordered_v2 = sort_reading_order(raw_results, alpha=0.8)
        text_v2 = "\n".join(t for _, t, _ in ordered_v2)
        comp_v2 = extract_composition_section(text_v2)
        tokens_v2 = tokenize(comp_v2)

        data = {
            "photo_name": photo_name,
            "category": cat,
            "comp_v1": comp_v1,
            "comp_v2": comp_v2,
            "tokens_v1": tokens_v1,
            "tokens_v2": tokens_v2,
            "is_comp_identical": comp_v1 == comp_v2,
            "is_tokens_identical": tokens_v1 == tokens_v2,
            "full_ocr_v1": text_v1,
            "full_ocr_v2": text_v2,
        }
        all_data.append(data)

    out_file = REPO_ROOT / "dataset" / "debug_output" / "targeted_regression_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print("SUCCESS_SAVED_JSON")

if __name__ == "__main__":
    main()
