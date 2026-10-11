"""Test column-aware reading order sorting algorithm."""

import json
from pathlib import Path
import numpy as np
import cv2
import easyocr

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
DEBUG_OUT = REPO_ROOT / "dataset" / "debug_output"

import sys
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH

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


def sort_reading_order_v2_column_aware(results: list, alpha: float = 0.8) -> list[tuple[list, str, float]]:
    """Column-aware reading order sorting.
    
    1. Group detections into lines by Y proximity (tolerance = 0.5 * mean_height).
    2. Within each line, sort left-to-right. Split line into segments when horizontal gap > alpha * mean_height.
    3. Group segments into vertical columns based on horizontal overlap / position.
    4. Sort columns left-to-right (by mean X center).
    5. Within each column, read top-to-bottom by line Y without interleaving.
    """
    if not results:
        return []

    detections = []
    heights = []
    for bbox, text, confidence in results:
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        height = max_y - min_y
        center_y = sum(ys) / len(ys)
        center_x = sum(xs) / len(xs)
        detections.append({
            "bbox": bbox,
            "text": text,
            "confidence": confidence,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "center_y": center_y,
            "center_x": center_x,
            "height": height
        })
        heights.append(height)

    mean_h = float(np.mean(heights)) if heights else 1.0
    tolerance_y = max(mean_h * 0.5, 1.0)
    gap_limit_x = max(mean_h * alpha, 1.0)

    # Step 1: Group detections into horizontal lines by Y
    lines = []
    for det in sorted(detections, key=lambda d: d["center_y"]):
        line = min(lines, key=lambda l: abs(l["center_y"] - det["center_y"]), default=None)
        if line is None or abs(line["center_y"] - det["center_y"]) > tolerance_y:
            lines.append({"center_y": det["center_y"], "items": [det]})
        else:
            line["items"].append(det)
            line["center_y"] = float(np.mean([item["center_y"] for item in line["items"]]))

    # Step 2: In each line, sort by min_x and split into segments if gap_x > gap_limit_x
    line_segments = []  # list of segments: {"center_y": float, "min_x": float, "max_x": float, "items": list}
    for line in sorted(lines, key=lambda l: l["center_y"]):
        sorted_items = sorted(line["items"], key=lambda d: d["min_x"])
        current_segment = [sorted_items[0]]
        for item in sorted_items[1:]:
            prev_item = current_segment[-1]
            gap_x = item["min_x"] - prev_item["max_x"]
            if gap_x > gap_limit_x:
                # Split segment
                seg_min_x = min(it["min_x"] for it in current_segment)
                seg_max_x = max(it["max_x"] for it in current_segment)
                line_segments.append({
                    "center_y": line["center_y"],
                    "min_x": seg_min_x,
                    "max_x": seg_max_x,
                    "center_x": (seg_min_x + seg_max_x) / 2.0,
                    "items": current_segment
                })
                current_segment = [item]
            else:
                current_segment.append(item)
        if current_segment:
            seg_min_x = min(it["min_x"] for it in current_segment)
            seg_max_x = max(it["max_x"] for it in current_segment)
            line_segments.append({
                "center_y": line["center_y"],
                "min_x": seg_min_x,
                "max_x": seg_max_x,
                "center_x": (seg_min_x + seg_max_x) / 2.0,
                "items": current_segment
            })

    # Step 3: Cluster segments into vertical columns
    # A column is a vertical cluster of segments that overlap or align horizontally.
    columns = []  # list of {"min_x": float, "max_x": float, "segments": list}
    for seg in sorted(line_segments, key=lambda s: (s["center_y"], s["min_x"])):
        # Find best matching column: check horizontal overlap or closest center_x
        best_col = None
        best_dist = float("inf")
        for col in columns:
            # Overlap check
            overlap = max(0, min(col["max_x"], seg["max_x"]) - max(col["min_x"], seg["min_x"]))
            if overlap > 0:
                # Directly overlaps
                best_col = col
                break
            else:
                # Check horizontal distance between segment center and column center
                col_center_x = (col["min_x"] + col["max_x"]) / 2.0
                dist = abs(seg["center_x"] - col_center_x)
                # If distance is small enough (e.g. within column width / gap)
                col_width = col["max_x"] - col["min_x"]
                if dist < max(col_width, gap_limit_x * 1.5) and dist < best_dist:
                    best_dist = dist
                    best_col = col

        if best_col is None:
            # New column
            columns.append({
                "min_x": seg["min_x"],
                "max_x": seg["max_x"],
                "segments": [seg]
            })
        else:
            best_col["segments"].append(seg)
            best_col["min_x"] = min(best_col["min_x"], seg["min_x"])
            best_col["max_x"] = max(best_col["max_x"], seg["max_x"])

    # Step 4: Sort columns from left to right
    # (or merge columns if two columns overlap significantly)
    # Sort segments inside each column from top to bottom by center_y
    ordered_detections = []
    columns_sorted = sorted(columns, key=lambda c: (c["min_x"] + c["max_x"]) / 2.0)
    for col in columns_sorted:
        col_segments = sorted(col["segments"], key=lambda s: s["center_y"])
        for seg in col_segments:
            for item in seg["items"]:
                ordered_detections.append((item["bbox"], item["text"], item["confidence"]))

    return ordered_detections

if __name__ == "__main__":
    # Test on cached melengkung_005 detections
    with open(DEBUG_OUT / "melengkung_005_detections.json", "r", encoding="utf-8") as f:
        melengkung_005 = json.load(f)
    raw_005 = [(d["bbox"], d["text"], d["conf"]) for d in melengkung_005]
    
    v1_res = sort_reading_order_v1(raw_005)
    v2_res = sort_reading_order_v2_column_aware(raw_005, alpha=0.8)
    
    print("=== BEFORE (v1 - Interleaved) melengkung_005 ===")
    print("\n".join(t for _, t, _ in v1_res))
    
    print("\n=== AFTER (v2 - Column-Aware alpha=0.8) melengkung_005 ===")
    print("\n".join(t for _, t, _ in v2_res))
