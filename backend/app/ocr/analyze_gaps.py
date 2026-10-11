"""Detailed analysis script for melengkung_005 and datar_002 reading order."""

import json
from pathlib import Path
import numpy as np

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
DEBUG_OUT = REPO_ROOT / "dataset" / "debug_output"

with open(DEBUG_OUT / "melengkung_005_detections.json", "r", encoding="utf-8") as f:
    melengkung_005 = json.load(f)

with open(DEBUG_OUT / "datar_002_detections.json", "r", encoding="utf-8") as f:
    datar_002 = json.load(f)

def run_current_sorting(detections):
    # Mimic sort_reading_order in reader.py
    heights = [d["height"] for d in detections]
    tolerance = max(float(np.mean(heights)) * 0.5, 1.0)
    
    # Format: (bbox, text, conf, center_y, min_x, original_obj)
    items = []
    for d in detections:
        items.append((d["bbox"], d["text"], d["conf"], d["center_y"], d["min_x"], d))
        
    lines = []
    for item in sorted(items, key=lambda x: x[3]):
        line = min(lines, key=lambda l: abs(l["center_y"] - item[3]), default=None)
        if line is None or abs(line["center_y"] - item[3]) > tolerance:
            lines.append({"center_y": item[3], "items": [item]})
        else:
            line["items"].append(item)
            line["center_y"] = float(np.mean([it[3] for it in line["items"]]))
            
    ordered_lines = []
    for line in sorted(lines, key=lambda l: l["center_y"]):
        sorted_line_items = sorted(line["items"], key=lambda it: it[4])
        ordered_lines.append({
            "center_y": line["center_y"],
            "items": [it[5] for it in sorted_line_items]
        })
    return ordered_lines, tolerance

print("==================================================")
print("HASIL PENGELOMPOKAN BARIS SAAT INI (melengkung_005):")
print("==================================================")
lines_005, tol_005 = run_current_sorting(melengkung_005)
print(f"Tolerance Y: {tol_005:.2f} px")
for line_idx, line in enumerate(lines_005, 1):
    items = line["items"]
    text_line = " ".join(f"[{it['id']}]{it['text']}" for it in items)
    xs = [(it["min_x"], it["max_x"]) for it in items]
    print(f"Line {line_idx:02d} (Y~{line['center_y']:.1f}): {text_line}")
    if len(items) > 1:
        # compute horizontal gaps between consecutive items in line
        gaps = []
        for i in range(len(items) - 1):
            gap_x = items[i+1]["min_x"] - items[i]["max_x"]
            gaps.append((items[i]["id"], items[i+1]["id"], gap_x))
        print(f"   -> X-gaps: {gaps}")

print("\n==================================================")
print("ANALISIS GAP HORIZONTAL NORMAL PADA datar_002:")
print("==================================================")
lines_datar, tol_datar = run_current_sorting(datar_002)
all_datar_gaps = []
for line in lines_datar:
    items = line["items"]
    if len(items) > 1:
        for i in range(len(items) - 1):
            gap_x = items[i+1]["min_x"] - items[i]["max_x"]
            all_datar_gaps.append({
                "line_y": line["center_y"],
                "left_id": items[i]["id"],
                "left_text": items[i]["text"],
                "left_max_x": items[i]["max_x"],
                "right_id": items[i+1]["id"],
                "right_text": items[i+1]["text"],
                "right_min_x": items[i+1]["min_x"],
                "gap_x": gap_x,
                "left_height": items[i]["height"],
                "right_height": items[i+1]["height"]
            })

gap_values = [g["gap_x"] for g in all_datar_gaps]
print(f"Total pasangan kata dalam baris pada datar_002: {len(gap_values)}")
print(f"Min gap: {np.min(gap_values)} px")
print(f"Median gap: {np.median(gap_values)} px")
print(f"Mean gap: {np.mean(gap_values):.2f} px")
print(f"p75 gap: {np.percentile(gap_values, 75):.2f} px")
print(f"p90 gap: {np.percentile(gap_values, 90):.2f} px")
print(f"p95 gap: {np.percentile(gap_values, 95):.2f} px")
print(f"Max gap: {np.max(gap_values)} px")
print("\nContoh beberapa gap di datar_002:")
for g in all_datar_gaps[:10]:
    print(f"  '{g['left_text']}' -> '{g['right_text']}' | gap: {g['gap_x']} px")

print("\nPasangan gap terbesar di datar_002:")
for g in sorted(all_datar_gaps, key=lambda x: x["gap_x"], reverse=True)[:5]:
    print(f"  '{g['left_text']}' -> '{g['right_text']}' | gap: {g['gap_x']} px (H: {g['left_height']},{g['right_height']})")

