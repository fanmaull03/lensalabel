"""Tahap 3 - Integrasi EasyOCR.

Reader di-load SEKALI (module-level singleton, lazy). Loading model paling
berat di CPU, jadi jangan pernah inisialisasi ulang per panggilan.

Downscale ke lebar maks 2000px di modul ini adalah optimasi performa OCR,
BUKAN bagian dari 5 tahap preprocessing resmi (lihat preprocessing/pipeline.py
yang urutannya fix sesuai proposal). Sengaja dipisah di sini.
"""

from __future__ import annotations

import cv2
import numpy as np
import os
from threading import Lock

# Knob: batas lebar sebelum readtext. Naik dari 1000 -> 2000 berdasarkan
# eksperimen ablasi (resolution_ablation_colab_summary.txt): 2000px jauh lebih
# baik dari 1000px, sementara resolusi penuh 12MP tidak menambah kualitas
# signifikan tapi makan 71.4 detik/foto. Kombinasi preprocessing (blur/CLAHE)
# di 2000px tidak berpengaruh signifikan, jadi pipeline preprocessing tetap
# 5 tahap penuh sesuai proposal.
MAX_OCR_WIDTH = 2000

_reader = None  # singleton, diisi saat pertama kali dibutuhkan
_reader_lock = Lock()


def get_reader():
    """Kembalikan instance EasyOCR tunggal (id+en). GPU opt-in via env."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr  # import di sini supaya modul lain tak ikut nunggu load model

                use_gpu = os.environ.get("EASYOCR_GPU", "0").strip().lower() in {"1", "true", "yes", "on"}
                _reader = easyocr.Reader(["id", "en"], gpu=use_gpu)
    return _reader


def _downscale(image: np.ndarray, max_width: int | None) -> np.ndarray:
    """Perkecil ke lebar max_width kalau kelebihan, jaga aspect ratio.

    max_width=None berarti pakai ukuran asli (tanpa downscale).
    """
    w = image.shape[1]
    if max_width is None or w <= max_width:
        return image
    scale = max_width / w
    new_size = (max_width, int(image.shape[0] * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def sort_reading_order(results: list, alpha: float = 0.8) -> list[tuple[list, str, float]]:
    """Sort EasyOCR detections with column-aware line segmentation.

    Each detection is ``(bbox, text, confidence)``.
    1. Lines are grouped by vertical midpoint (tolerance: 0.5 * mean_height).
    2. In each line, items are split into segments when horizontal gap > alpha * mean_height.
    3. Segments are clustered into vertical columns (left-to-right without interleave).
    4. Within each column, text is ordered top-to-bottom.
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
        detections.append({
            "bbox": bbox,
            "text": text,
            "confidence": confidence,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "center_y": sum(ys) / len(ys),
            "center_x": sum(xs) / len(xs),
            "height": height,
        })
        heights.append(height)

    mean_h = float(np.mean(heights)) if heights else 1.0
    tolerance_y = max(mean_h * 0.5, 1.0)
    gap_limit_x = max(mean_h * alpha, 1.0)

    # Step 1: Group detections into horizontal lines by vertical proximity
    lines: list[dict] = []
    for det in sorted(detections, key=lambda d: d["center_y"]):
        line = min(lines, key=lambda l: abs(l["center_y"] - det["center_y"]), default=None)
        if line is None or abs(line["center_y"] - det["center_y"]) > tolerance_y:
            lines.append({"center_y": det["center_y"], "items": [det]})
        else:
            line["items"].append(det)
            line["center_y"] = float(np.mean([item["center_y"] for item in line["items"]]))

    # Step 2: In each line, sort left-to-right and split on horizontal gaps > gap_limit_x
    line_segments: list[dict] = []
    for line in sorted(lines, key=lambda l: l["center_y"]):
        sorted_items = sorted(line["items"], key=lambda d: d["min_x"])
        current_segment = [sorted_items[0]]
        for item in sorted_items[1:]:
            prev_item = current_segment[-1]
            gap_x = item["min_x"] - prev_item["max_x"]
            if gap_x > gap_limit_x:
                seg_min_x = min(it["min_x"] for it in current_segment)
                seg_max_x = max(it["max_x"] for it in current_segment)
                line_segments.append({
                    "center_y": line["center_y"],
                    "min_x": seg_min_x,
                    "max_x": seg_max_x,
                    "center_x": (seg_min_x + seg_max_x) / 2.0,
                    "items": current_segment,
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
                "items": current_segment,
            })

    # Step 3: Cluster segments across lines into vertical columns
    columns: list[dict] = []
    for seg in sorted(line_segments, key=lambda s: (s["center_y"], s["min_x"])):
        best_col = None
        best_dist = float("inf")
        for col in columns:
            overlap = max(0, min(col["max_x"], seg["max_x"]) - max(col["min_x"], seg["min_x"]))
            if overlap > 0:
                best_col = col
                break
            col_center_x = (col["min_x"] + col["max_x"]) / 2.0
            dist = abs(seg["center_x"] - col_center_x)
            col_width = col["max_x"] - col["min_x"]
            if dist < max(col_width, gap_limit_x * 1.5) and dist < best_dist:
                best_dist = dist
                best_col = col

        if best_col is None:
            columns.append({
                "min_x": seg["min_x"],
                "max_x": seg["max_x"],
                "segments": [seg],
            })
        else:
            best_col["segments"].append(seg)
            best_col["min_x"] = min(best_col["min_x"], seg["min_x"])
            best_col["max_x"] = max(best_col["max_x"], seg["max_x"])

    # Step 4: Sort columns left-to-right, and segments within each column top-to-bottom
    ordered: list[tuple[list, str, float]] = []
    columns_sorted = sorted(columns, key=lambda c: (c["min_x"] + c["max_x"]) / 2.0)
    for col in columns_sorted:
        col_segments = sorted(col["segments"], key=lambda s: s["center_y"])
        for seg in col_segments:
            for item in seg["items"]:
                ordered.append((item["bbox"], item["text"], item["confidence"]))
    return ordered


def extract_text(image: np.ndarray, max_width: int | None = MAX_OCR_WIDTH) -> str:
    """Jalankan OCR, gabungkan semua deteksi jadi satu string.

    max_width: batas lebar sebelum OCR (None = ukuran asli). Pemisahan per
    bahan ditangani di tahap tokenisasi terpisah, bukan di sini. Deteksi OCR
    diurutkan berdasarkan posisi bounding box sebelum digabungkan.
    """
    results = get_reader().readtext(_downscale(image, max_width), detail=1)
    ordered = sort_reading_order(results)
    return "\n".join(text for _, text, _ in ordered)
