"""Read-only quality audit for the 100 melengkung photos.

Run from backend/:
  python -m app.ocr.audit_melengkung_quality

The audit uses the production decode/preprocessing/OCR path and writes only:
  dataset/debug_output/melengkung_quality_audit.csv
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import cv2
import numpy as np

from app.api.routes_identify import decode_image_bytes
from app.ocr.reader import MAX_OCR_WIDTH, extract_text
from app.preprocessing.pipeline import preprocess

REPO_ROOT = Path(__file__).resolve().parents[3]
PHOTO_DIR = REPO_ROOT / "dataset" / "raw_photos" / "melengkung"
OUTPUT_CSV = REPO_ROOT / "dataset" / "debug_output" / "melengkung_quality_audit.csv"
EXPECTED_PHOTO_COUNT = 100
OCR_SUSPICIOUS_PERCENTILE = 10


def overexposed_percentage(image: np.ndarray) -> float:
    """Return the percentage of pixels with grayscale intensity above 240."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray > 240) * 100)


def text_suspicious(text: str, short_length_threshold: float) -> bool:
    """Flag short or visibly noisy OCR as a review signal, not a verdict."""
    if len(text) < short_length_threshold:
        return True
    if not text.strip():
        return True

    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    alphanumeric_ratio = sum(char.isalnum() for char in compact) / len(compact)
    if alphanumeric_ratio < 0.55:
        return True

    words = text.split()
    short_word_ratio = sum(len(word) <= 2 for word in words) / max(len(words), 1)
    return len(words) >= 8 and short_word_ratio > 0.55


def percentile(values: list[float], value: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), value))


def audit_photo(path: Path) -> dict:
    image = decode_image_bytes(path.read_bytes())
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    overexposed_pct = overexposed_percentage(image)
    ocr_text = extract_text(preprocess(image), max_width=MAX_OCR_WIDTH)
    return {
        "filename": path.name,
        "laplacian_variance": round(laplacian_variance, 4),
        "overexposed_pct": round(overexposed_pct, 4),
        "ocr_char_length": len(ocr_text),
        "ocr_suspicious_flag": False,
        "ocr_text_preview": ocr_text[:160].replace("\n", " "),
        "_ocr_text": ocr_text,
    }


def main() -> None:
    photos = sorted(PHOTO_DIR.glob("melengkung_*.jpeg"))
    if len(photos) != EXPECTED_PHOTO_COUNT:
        raise RuntimeError(
            f"Diharapkan {EXPECTED_PHOTO_COUNT} foto .jpeg, ditemukan {len(photos)} di {PHOTO_DIR}"
        )

    print(f"Audit {len(photos)} foto; OCR max width={MAX_OCR_WIDTH}", flush=True)
    rows = []
    for index, path in enumerate(photos, start=1):
        print(f"[{index:03d}/{len(photos):03d}] {path.name}", flush=True)
        rows.append(audit_photo(path))

    lengths = [row["ocr_char_length"] for row in rows]
    blur_cutoff = percentile([row["laplacian_variance"] for row in rows], 10)
    short_cutoff = percentile(lengths, OCR_SUSPICIOUS_PERCENTILE)
    overexposure_cutoff = percentile([row["overexposed_pct"] for row in rows], 90)

    for row in rows:
        row["blur_flag"] = row["laplacian_variance"] <= blur_cutoff
        row["overexposed_flag"] = row["overexposed_pct"] >= overexposure_cutoff
        row["ocr_suspicious_flag"] = text_suspicious(row["_ocr_text"], short_cutoff)
        row["high_risk_flag"] = row["blur_flag"] or row["ocr_suspicious_flag"]
        row["risk_score"] = sum(
            [row["blur_flag"], row["overexposed_flag"], row["ocr_suspicious_flag"]]
        )
        row["risk_level"] = (
            "high" if row["high_risk_flag"] else "review" if row["overexposed_flag"] else "low"
        )
        del row["_ocr_text"]

    rows.sort(
        key=lambda row: (
            -row["high_risk_flag"],
            -row["risk_score"],
            row["laplacian_variance"],
        )
    )
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "filename",
        "laplacian_variance",
        "overexposed_pct",
        "ocr_char_length",
        "ocr_suspicious_flag",
        "blur_flag",
        "overexposed_flag",
        "high_risk_flag",
        "risk_score",
        "risk_level",
        "ocr_text_preview",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    high_risk = sum(row["high_risk_flag"] for row in rows)
    print(f"\nBlur cutoff p10: {blur_cutoff:.4f}")
    print(f"OCR length cutoff p10: {short_cutoff:.1f} karakter")
    print(f"Overexposure cutoff p90: {overexposure_cutoff:.4f}%")
    print(f"Berisiko tinggi: {high_risk}/{len(rows)}")
    print("\n10 foto paling blur:")
    for row in sorted(rows, key=lambda item: item["laplacian_variance"])[:10]:
        print(f"  {row['filename']}: {row['laplacian_variance']:.4f}")
    print(f"\nCSV: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
