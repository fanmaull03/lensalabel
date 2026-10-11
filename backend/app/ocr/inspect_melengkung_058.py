import sys
from pathlib import Path
import cv2, easyocr
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, _find_marker, _find_closing_marker, OPEN_MARKERS

def main():
    reader = easyocr.Reader(["id", "en"], gpu=False)
    p_path = REPO_ROOT / "dataset" / "raw_photos" / "melengkung" / "melengkung_058.jpeg"
    img = cv2.imread(str(p_path))
    prep = preprocess(img)
    ocr_img = _downscale(prep, MAX_OCR_WIDTH)
    raw = reader.readtext(ocr_img, detail=1)

    print(f"Total raw detections: {len(raw)}")
    heights = [max(p[1] for p in b) - min(p[1] for p in b) for b, _, _ in raw]
    mean_h = np.mean(heights)
    print(f"Mean height: {mean_h:.1f}, gap_limit_x (0.8*H): {mean_h*0.8:.1f}")

    ordered = sort_reading_order(raw, alpha=0.8)
    print("\n=== ORDERED V2 DETECTIONS ===")
    for i, (bbox, text, conf) in enumerate(ordered):
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        print(f"{i:2d}: x=[{min(xs):4.0f}, {max(xs):4.0f}] y=[{min(ys):4.0f}, {max(ys):4.0f}] (cx={(min(xs)+max(xs))/2:.0f}, cy={(min(ys)+max(ys))/2:.0f}) -> {text}")

    full_txt = "\n".join(t for _, t, _ in ordered)
    words = full_txt.split()
    open_idx = _find_marker(words, OPEN_MARKERS)
    close_idx = _find_closing_marker(words, start=open_idx + 1 if open_idx is not None else 0)

    print(f"\nOpen marker: {open_idx} -> '{words[open_idx] if open_idx is not None else None}'")
    print(f"Close marker: {close_idx} -> '{words[close_idx] if close_idx is not None else None}'")
    print("\nExtracted text V2:")
    print(extract_composition_section(full_txt))

if __name__ == "__main__":
    main()
