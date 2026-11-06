"""OCR-only pass for the frozen 160-photo evaluation split; computes no metrics."""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import os
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.frozen_config import load_config  # noqa: E402


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def installed_opencv_distributions() -> dict[str, str]:
    names = ("opencv-python", "opencv-python-headless", "opencv-contrib-python")
    return {name: value for name in names if (value := package_version(name)) != "not-installed"}


def verify_sha256(path: Path, expected: str, label: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual.casefold() != str(expected).casefold():
        raise RuntimeError(f"Hash {label} tidak cocok: expected={expected}, actual={actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-imports", action="store_true",
                        help="Validasi impor tanpa membaca foto atau menjalankan OCR.")
    parser.add_argument("--config", default=None,
                        help="Nama berkas konfigurasi beku, mis. config_frozen_v2.json. Default: config_frozen.json.")
    args = parser.parse_args()
    config = load_config(require_frozen=not args.check_imports, config_name=args.config)
    config_path = ROOT / "evaluation" / (args.config or "config_frozen.json")
    config_hash_path = config_path.with_name(config_path.name.replace(".json", ".sha256"))
    opencv_distributions = installed_opencv_distributions()
    import cv2
    import torch

    print({
        "easyocr": package_version("easyocr"),
        "torch": package_version("torch"),
        "torch_cuda_available": torch.cuda.is_available(),
        "opencv_distributions": installed_opencv_distributions(),
        "cv2.__version__": cv2.__version__,
        "cv2.__file__": str(cv2.__file__),
    }, flush=True)
    if not args.check_imports:
        if len(opencv_distributions) != 1:
            raise RuntimeError("Evaluasi dihentikan: harus ada tepat satu distribusi OpenCV. Terpasang: " + repr(opencv_distributions))
        if not config_hash_path.is_file():
            raise RuntimeError("config_frozen.sha256 tidak ada; integritas config belum dapat diverifikasi.")
        expected_config_hash = config_hash_path.read_text(encoding="utf-8-sig").strip().split()[0]
        verify_sha256(config_path, expected_config_hash, "config_frozen.json")
        for field_path, field_hash, label in (("kb_path", "kb_sha256", "KB"),
                                               ("evaluation_gt_path", "evaluation_gt_sha256", "evaluation GT")):
            path = ROOT / str(config[field_path])
            if not path.is_file() or not config.get(field_hash):
                raise RuntimeError(f"Path/hash {label} tidak lengkap di config_frozen.json.")
            verify_sha256(path, str(config[field_hash]), label)
    if args.check_imports and len(opencv_distributions) != 1:
        print("Import check saja: distribusi OpenCV ganda dicatat; guard produksi tetap aktif.")

    # get_reader() checks this environment variable lazily on first OCR call.
    os.environ["EASYOCR_GPU"] = "1" if torch.cuda.is_available() else "0"
    backend = ROOT / "backend"
    sys.path.insert(0, str(backend))
    from app.ocr.reader import extract_text  # noqa: E402
    from app.preprocessing.pipeline import (  # noqa: E402
        deskew, enhance_contrast, reduce_noise, to_grayscale,
    )

    if args.check_imports:
        print("Import check selesai; foto tidak dibaca dan OCR tidak dijalankan.")
        return

    split_path = ROOT / "evaluation" / "splits" / "evaluation_set.csv"
    photos_root = ROOT / "dataset" / "raw_photos"
    output_path = ROOT / "evaluation" / "results" / "evaluation_ocr" / "evaluation_ocr_160.csv"
    with split_path.open(encoding="utf-8-sig", newline="") as stream:
        split_rows = list(csv.DictReader(stream))
    filenames = {row["filename"] for row in split_rows}
    if len(split_rows) != 160 or len(filenames) != 160:
        raise RuntimeError(f"Expected 160 unique evaluation photos; found {len(split_rows)} rows / {len(filenames)} names")

    expected_steps = ["grayscale", "blur", "CLAHE", "deskew"]
    if config["preprocessing_order"] != expected_steps:
        raise ValueError(f"Urutan preprocessing config tidak didukung: {config['preprocessing_order']}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["filename", "category", "ocr_text", "ocr_runtime_seconds", "preprocess_runtime_seconds",
              "max_ocr_width", "adaptive_threshold", "easyocr_version", "torch_version",
              "opencv_version", "opencv_module_path"]
    rows_out = []
    for index, item in enumerate(split_rows, start=1):
        filename, condition = item["filename"], item["category"]
        image_path = photos_root / condition / filename
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Foto evaluasi hilang/tidak terbaca: {image_path}")

        started = time.perf_counter()
        transformed = enhance_contrast(reduce_noise(to_grayscale(image)))
        if bool(config["adaptive_threshold"]):
            transformed = cv2.adaptiveThreshold(
                transformed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5,
            )
        transformed = deskew(transformed)
        preprocess_seconds = time.perf_counter() - started
        started = time.perf_counter()
        text = extract_text(transformed, max_width=int(config["max_ocr_width"]))
        ocr_seconds = time.perf_counter() - started
        rows_out.append({
            "filename": filename, "category": condition, "ocr_text": text,
            "ocr_runtime_seconds": ocr_seconds, "preprocess_runtime_seconds": preprocess_seconds,
            "max_ocr_width": config["max_ocr_width"],
            "adaptive_threshold": config["adaptive_threshold"],
            "easyocr_version": package_version("easyocr"), "torch_version": package_version("torch"),
            "opencv_version": cv2.__version__, "opencv_module_path": str(cv2.__file__),
        })
        print(f"[{index}/160] {filename}: OCR {ocr_seconds:.2f}s", flush=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"OCR selesai; teks dan waktu tersimpan di {output_path}")
    print("Metrik/prediksi bahan tidak dihitung oleh skrip ini.")


if __name__ == "__main__":
    main()
