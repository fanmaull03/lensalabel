"""Inspect column 1 vs column 2 in melengkung_005."""

import json
from pathlib import Path
import numpy as np

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
DEBUG_OUT = REPO_ROOT / "dataset" / "debug_output"

with open(DEBUG_OUT / "melengkung_005_detections.json", "r", encoding="utf-8") as f:
    melengkung_005 = json.load(f)

# Sort by center_y
melengkung_005.sort(key=lambda d: d["center_y"])

print("DETEKSI DI MELENGKUNG_005 DIURUTKAN BERDASARKAN Y:")
print(f"{'ID':<4} | {'X min..max':<14} | {'Y min..max':<14} | {'W x H':<10} | {'Text'}")
print("-" * 75)
for d in melengkung_005:
    col = "KIRI (Nutrition)" if d["max_x"] < 765 else "TENGAH/KANAN (Komposisi/Info)"
    print(f"#{d['id']:<3} | X:{d['min_x']:4d}..{d['max_x']:4d} | Y:{d['min_y']:4d}..{d['max_y']:4d} | {d['width']:3d}x{d['height']:2d} | [{col}] {d['text']}")

