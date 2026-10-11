"""Save preprocessing stages and OCR text for curved-package diagnostics.

This runner mirrors the current backend path without changing production code:
  cv2.imdecode -> preprocess() -> EasyOCR (default max width)

Run from backend/:
  python -m app.ocr.run_preprocessing_steps_debug
  python -m app.ocr.run_preprocessing_steps_debug --photo melengkung_026.jpeg

Outputs are written under dataset/debug_output/preprocessing_steps/<photo>/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from app.api.routes_identify import decode_image_bytes
from app.ocr.reader import MAX_OCR_WIDTH, extract_text
from app.preprocessing.pipeline import STAGES

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "dataset" / "raw_photos" / "melengkung"
OUTPUT_ROOT = REPO_ROOT / "dataset" / "debug_output" / "preprocessing_steps"
DEFAULT_PHOTOS = (
    "melengkung_001.jpeg",
    "melengkung_026.jpeg",
    "melengkung_050.jpeg",
    "melengkung_100.jpeg",
)


def decode_like_backend(path: Path) -> np.ndarray:
    """Decode bytes through the same EXIF-aware helper used by the API."""
    try:
        return decode_image_bytes(path.read_bytes())
    except ValueError as exc:
        raise ValueError(f"Gagal mendecode gambar: {path}") from exc


def save_stage(directory: Path, number: int, name: str, image: np.ndarray) -> None:
    output = directory / f"{number:02d}_{name}.png"
    if not cv2.imwrite(str(output), image):
        raise OSError(f"Gagal menulis {output}")


def process(path: Path, output_root: Path) -> None:
    image = decode_like_backend(path)
    output_dir = output_root / path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    height, width = image.shape[:2]
    print(f"\n=== {path.name} ({width}x{height}) ===", flush=True)
    save_stage(output_dir, 1, "decoded_backend_bgr", image)

    current = image
    for number, (name, stage) in enumerate(STAGES, start=2):
        current = stage(current)
        save_stage(output_dir, number, name, current)

    # Keep an explicit final copy to make the EasyOCR input unambiguous.
    save_stage(output_dir, 6, "easyocr_input", current)

    text = extract_text(current)
    (output_dir / "ocr.txt").write_text(text, encoding="utf-8")
    (output_dir / "image_info.txt").write_text(
        f"source={path}\nwidth={width}\nheight={height}\n"
        f"ocr_max_width={MAX_OCR_WIDTH}\npreprocessing_stages={len(STAGES)}\n",
        encoding="utf-8",
    )
    print(f"OCR ({len(text)} karakter): {text}", flush=True)
    print(f"Output: {output_dir}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", help="Process one filename from raw_photos/melengkung")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
        help="Output directory for stage images and OCR text.",
    )
    args = parser.parse_args()
    photos = (args.photo,) if args.photo else DEFAULT_PHOTOS

    for filename in photos:
        path = RAW_DIR / filename
        if not path.is_file():
            print(f"[skip] file tidak ditemukan: {path}", file=sys.stderr)
            continue
        process(path, args.output_root)


if __name__ == "__main__":
    main()
