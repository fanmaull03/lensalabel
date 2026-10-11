"""Analyze inter-word horizontal gaps in normal sentences across dataset photos."""

import json
from pathlib import Path
import numpy as np

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
DEBUG_OUT = REPO_ROOT / "dataset" / "debug_output"

with open(DEBUG_OUT / "melengkung_005_detections.json", "r", encoding="utf-8") as f:
    melengkung_005 = json.load(f)

with open(DEBUG_OUT / "datar_002_detections.json", "r", encoding="utf-8") as f:
    datar_002 = json.load(f)

# Let's inspect intra-sentence words in melengkung_005 (only Column 2 words)
col2_005 = [d for d in melengkung_005 if d["min_x"] >= 780]

# Group col2 into lines
heights_005 = [d["height"] for d in col2_005]
tol_005 = max(float(np.mean(heights_005)) * 0.5, 1.0)
items = [(d["bbox"], d["text"], d["conf"], d["center_y"], d["min_x"], d) for d in col2_005]

lines = []
for item in sorted(items, key=lambda x: x[3]):
    line = min(lines, key=lambda l: abs(l["center_y"] - item[3]), default=None)
    if line is None or abs(line["center_y"] - item[3]) > tol_005:
        lines.append({"center_y": item[3], "items": [item]})
    else:
        line["items"].append(item)
        line["center_y"] = float(np.mean([it[3] for it in line["items"]]))

col2_gaps = []
print("=== INTRA-COLUMN GAPS (KOLOM KOMPOSISI melengkung_005) ===")
for line in sorted(lines, key=lambda l: l["center_y"]):
    line_items = sorted([it[5] for it in line["items"]], key=lambda x: x["min_x"])
    if len(line_items) > 1:
        line_text = " | ".join(f"'{it['text']}'" for it in line_items)
        print(f"Line (Y~{line['center_y']:.1f}): {line_text}")
        for i in range(len(line_items) - 1):
            left = line_items[i]
            right = line_items[i+1]
            gap = right["min_x"] - left["max_x"]
            col2_gaps.append((gap, left["text"], right["text"], left["height"], right["height"]))
            print(f"   gap: {gap:3d} px between '{left['text']}' (max_x={left['max_x']}) and '{right['text']}' (min_x={right['min_x']})")

gap_vals = [g[0] for g in col2_gaps]
print(f"\nDistribusi Gap Normal antar-kata satu kalimat di melengkung_005:")
print(f"Count: {len(gap_vals)}")
print(f"Min: {np.min(gap_vals)} px")
print(f"Median: {np.median(gap_vals)} px")
print(f"Mean: {np.mean(gap_vals):.2f} px")
print(f"Max: {np.max(gap_vals)} px")
print(f"p90: {np.percentile(gap_vals, 90):.2f} px")

