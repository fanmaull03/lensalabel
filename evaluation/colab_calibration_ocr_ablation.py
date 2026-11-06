"""Colab script prepared to measure CER/WER on the 40 calibration photos only.

Run in a Colab copy containing this repository layout and dataset photos. The
script refuses any split except the exact 40-photo calibration manifest.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version

OPENCV_DISTRIBUTIONS = ("opencv-python", "opencv-python-headless", "opencv-contrib-python")


def installed_opencv_distributions() -> dict[str, str]:
    found = {}
    for distribution in OPENCV_DISTRIBUTIONS:
        try:
            found[distribution] = version(distribution)
        except PackageNotFoundError:
            pass
    return found


_opencv_installed_at_import = installed_opencv_distributions()
if len(_opencv_installed_at_import) > 1:
    raise RuntimeError("Beberapa distribusi OpenCV terpasang: " + repr(_opencv_installed_at_import)
                       + ". Sisakan tepat satu paket OpenCV, restart runtime, lalu jalankan ulang.")

import cv2
import jiwer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ocr.reader import extract_text  # noqa: E402
from app.preprocessing.pipeline import deskew, enhance_contrast, reduce_noise, to_grayscale  # noqa: E402
from app.tokenizer.tokenizer import extract_composition_section, OPEN_MARKERS, _find_marker  # noqa: E402

SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
RAW = ROOT / "dataset/raw_photos"
OUT = ROOT / "evaluation/results/calibration_ocr_ablation"
WIDTHS = (1000, 1500, 2000)
ADAPTIVE_OPTIONS = (False, True)


def preprocess_variant(image, adaptive: bool):
    gray = to_grayscale(image)
    smooth = reduce_noise(gray)
    contrast = enhance_contrast(smooth)
    if adaptive:
        contrast = cv2.adaptiveThreshold(contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         cv2.THRESH_BINARY, 31, 5)
    return deskew(contrast)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def normalize_for_metrics(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(" " if unicodedata.category(char).startswith("P") else char for char in text)
    return re.sub(r"\s+", " ", text).strip()


def local_edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Edit distance to the best contiguous OCR span; outer OCR is free."""
    previous = [0] * (len(hypothesis) + 1)
    for i, ref_item in enumerate(reference, start=1):
        current = [i] + [0] * len(hypothesis)
        for j, hyp_item in enumerate(hypothesis, start=1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1,
                             previous[j - 1] + (ref_item != hyp_item))
        previous = current
    return min(previous) if previous else len(reference)


def local_cer_wer(reference: str, hypothesis: str) -> tuple[float, float]:
    ref_chars, hyp_chars = list(reference), list(hypothesis)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    return (local_edit_distance(ref_chars, hyp_chars) / max(1, len(ref_chars)),
            local_edit_distance(ref_words, hyp_words) / max(1, len(ref_words)))


def main() -> None:
    with SPLIT.open(encoding="utf-8-sig", newline="") as f:
        split = list(csv.DictReader(f))
    if len(split) != 40 or len({r["filename"] for r in split}) != 40:
        raise RuntimeError("Ablation hanya menerima tepat 40 foto pada calibration_set.csv.")
    with TRANSCRIPTS.open(encoding="utf-8-sig", newline="") as f:
        gt = {r["filename"]: r["ground_truth_text"] for r in csv.DictReader(f)
              if r["filename"] in {x["filename"] for x in split}}
    if set(gt) != {r["filename"] for r in split}:
        raise RuntimeError("Transcript tidak lengkap untuk 40 foto kalibrasi.")

    details = []
    totals = defaultdict(lambda: {"cer_composition": [], "wer_composition": [],
                                  "cer_full": [], "wer_full": [], "cer_local": [], "wer_local": [],
                                  "open_marker_missing": 0})
    versions = {"easyocr": package_version("easyocr"), "torch": package_version("torch"),
                "opencv-python-headless": package_version("opencv-python-headless"),
                "opencv-python": package_version("opencv-python"), "opencv_runtime": cv2.__version__,
                "opencv-contrib-python": package_version("opencv-contrib-python"),
                "opencv_module_path": str(cv2.__file__),
                "python": sys.version}
    print("Runtime paket: " + json.dumps({"easyocr": versions["easyocr"], "torch": versions["torch"],
                                          "cv2.__version__": versions["opencv_runtime"],
                                          "cv2.__file__": versions["opencv_module_path"],
                                          "opencv_distributions": installed_opencv_distributions()}, ensure_ascii=False),
          flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for photo_index, row in enumerate(split, start=1):
        filename, condition = row["filename"], row["category"]
        photo = RAW / condition / filename
        image = cv2.imread(str(photo))
        if image is None:
            raise FileNotFoundError(f"Foto kalibrasi tidak dapat dibaca: {photo}")
        for adaptive in ADAPTIVE_OPTIONS:
            preprocess_started = time.perf_counter()
            prepared = preprocess_variant(image.copy(), adaptive)
            preprocess_elapsed = time.perf_counter() - preprocess_started
            for width in WIDTHS:
                started = time.perf_counter()
                hypothesis = extract_text(prepared, max_width=width)
                elapsed = time.perf_counter() - started
                composition = extract_composition_section(hypothesis)
                cer_full = float(jiwer.cer(gt[filename], hypothesis))
                wer_full = float(jiwer.wer(gt[filename], hypothesis))
                normalized_gt = normalize_for_metrics(gt[filename])
                normalized_composition = normalize_for_metrics(composition)
                cer_composition = float(jiwer.cer(normalized_gt, normalized_composition))
                wer_composition = float(jiwer.wer(normalized_gt, normalized_composition))
                normalized_hypothesis = normalize_for_metrics(hypothesis)
                cer_local, wer_local = local_cer_wer(normalized_gt, normalized_hypothesis)
                open_marker_missing = _find_marker(hypothesis.split(), OPEN_MARKERS) is None
                key = (width, adaptive, condition)
                totals[key]["cer_full"].append(cer_full); totals[key]["wer_full"].append(wer_full)
                totals[key]["cer_composition"].append(cer_composition)
                totals[key]["wer_composition"].append(wer_composition)
                totals[key]["cer_local"].append(cer_local); totals[key]["wer_local"].append(wer_local)
                totals[key]["open_marker_missing"] += int(open_marker_missing)
                details.append({"filename": filename, "condition": condition, "max_ocr_width": width,
                                "adaptive_threshold": adaptive,
                                "config_key": f"width_{width}_adaptive_{'on' if adaptive else 'off'}",
                                "preprocess_runtime_seconds": preprocess_elapsed,
                                "cer_teks_penuh": cer_full, "wer_teks_penuh": wer_full,
                                "cer_komposisi": cer_composition, "wer_komposisi": wer_composition,
                                "cer_lokal": cer_local, "wer_lokal": wer_local,
                                "penanda_pembuka_terdeteksi": not open_marker_missing,
                                "teks_komposisi_ocr": composition,
                                "normalisasi_metrik": "NFKC, casefold, tanda baca menjadi spasi, whitespace diringkas; identik pada GT dan OCR",
                                "ocr_runtime_seconds": elapsed,
                                "configuration_runtime_seconds": preprocess_elapsed + elapsed,
                                "easyocr_version": versions["easyocr"], "torch_version": versions["torch"],
                                "opencv_headless_version": versions["opencv-python-headless"],
                                "opencv_python_version": versions["opencv-python"],
                                "opencv_runtime_version": versions["opencv_runtime"],
                                "ground_truth_text": gt[filename], "ocr_text": hypothesis})
        print(f"[{photo_index}/40] selesai {filename}", flush=True)

    summary = []
    for width in WIDTHS:
        for adaptive in ADAPTIVE_OPTIONS:
            for condition in ("keseluruhan", "datar", "melengkung"):
                keys = [(width, adaptive, c) for c in ("datar", "melengkung") if condition == "keseluruhan" or c == condition]
                count = sum(len(totals[key]["cer_composition"]) for key in keys)
                summary.append({"max_ocr_width": width, "adaptive_threshold": adaptive,
                                "condition": condition, "n_photos": count,
                                "mean_cer_komposisi": sum(v for key in keys for v in totals[key]["cer_composition"]) / count,
                                "mean_wer_komposisi": sum(v for key in keys for v in totals[key]["wer_composition"]) / count,
                                "mean_cer_teks_penuh": sum(v for key in keys for v in totals[key]["cer_full"]) / count,
                                "mean_wer_teks_penuh": sum(v for key in keys for v in totals[key]["wer_full"]) / count,
                                "mean_cer_lokal": sum(v for key in keys for v in totals[key]["cer_local"]) / count,
                                "mean_wer_lokal": sum(v for key in keys for v in totals[key]["wer_local"]) / count,
                                "penanda_pembuka_tidak_terdeteksi": sum(totals[key]["open_marker_missing"] for key in keys),
                                "normalisasi": "NFKC, casefold, tanda baca menjadi spasi, whitespace diringkas"})
    write_csv(OUT / "ocr_ablation_detail.csv", details)
    write_csv(OUT / "ocr_ablation_summary.csv", summary)
    (OUT / "environment_versions.json").write_text(json.dumps(versions, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")
    print(f"Selesai. Output hanya berisi 40 foto kalibrasi: {OUT}")


if __name__ == "__main__":
    main()
