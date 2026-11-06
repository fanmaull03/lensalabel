"""Profiling waktu per tahap pipeline OCR – read-only, tidak mengubah apapun.

Menjalankan pipeline lengkap terhadap 10 foto (campuran datar dan melengkung),
mencatat durasi TIAP tahap secara terpisah, dan mencetak hasilnya sebagai tabel.

Foto melengkung_099 dan melengkung_100 (tercatat >100 detik di log regresi)
sengaja dimasukkan supaya bisa diinvestigasi kenapa jauh lebih lambat.

Cara pakai (dari root folder project):
  python evaluation/profile_pipeline_timing.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# --- Path setup (sama dengan run_ocr_evaluation.py) --------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.preprocessing.pipeline import (  # noqa: E402
    to_grayscale,
    reduce_noise,
    enhance_contrast,
    deskew,
)
from app.ocr.reader import (  # noqa: E402
    get_reader,
    _downscale,
    sort_reading_order,
    MAX_OCR_WIDTH,
)
from app.tokenizer.tokenizer import (  # noqa: E402
    extract_composition_section,
    tokenize,
)

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
RAW_PHOTOS_DIR = DATASET_DIR / "raw_photos"

# --- 10 foto sampel: 5 datar + 3 melengkung biasa + 2 melengkung lambat ------
SAMPLE_PHOTOS: list[tuple[str, str]] = [
    # (kategori subfolder, nama file)
    ("datar", "datar_001.jpeg"),
    ("datar", "datar_010.jpeg"),
    ("datar", "datar_025.jpeg"),
    ("datar", "datar_050.jpeg"),
    ("datar", "datar_075.jpeg"),
    ("melengkung", "melengkung_001.jpeg"),
    ("melengkung", "melengkung_025.jpeg"),
    ("melengkung", "melengkung_050.jpeg"),
    # Dua foto yang tercatat sangat lambat (>100 detik):
    ("melengkung", "melengkung_099.jpeg"),
    ("melengkung", "melengkung_100.jpeg"),
]

# Nama-nama kolom tahap (urut sesuai pipeline)
STAGE_NAMES = [
    "imread",
    "grayscale",
    "blur",
    "clahe",
    "deskew",
    "downscale",
    "easyocr_readtext",
    "sort_reading_order",
    "extract+tokenize",
]


def _measure(fn, *args, **kwargs):
    """Jalankan fn, kembalikan (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


def profile_single(
    photo_path: Path,
    reader,
) -> dict:
    """Profil satu foto, kembalikan dict berisi timing + metadata diagnostik."""

    timings: dict[str, float] = {}
    file_size_bytes = photo_path.stat().st_size

    # 1. imread (cv2.imread, bukan imdecode, tapi secara fungsional identik
    #    untuk file di disk; yang mau diukur = waktu decode JPEG -> array)
    image, t = _measure(cv2.imread, str(photo_path))
    timings["imread"] = t
    if image is None:
        print(f"  GAGAL membaca {photo_path}")
        return {"photo": photo_path.name, "error": "imread gagal"}

    h_orig, w_orig = image.shape[:2]

    # 2-5. Empat tahap preprocessing, masing-masing terpisah
    gray, t = _measure(to_grayscale, image)
    timings["grayscale"] = t

    blurred, t = _measure(reduce_noise, gray)
    timings["blur"] = t

    contrast, t = _measure(enhance_contrast, blurred)
    timings["clahe"] = t

    deskewed, t = _measure(deskew, contrast)
    timings["deskew"] = t

    # 6. Downscale sebelum OCR
    downscaled, t = _measure(_downscale, deskewed, MAX_OCR_WIDTH)
    timings["downscale"] = t
    h_ocr, w_ocr = downscaled.shape[:2]

    # 7. EasyOCR readtext — MURNI pemanggilan reader.readtext saja
    t0 = time.perf_counter()
    raw_results = reader.readtext(downscaled, detail=1)
    timings["easyocr_readtext"] = time.perf_counter() - t0
    n_regions = len(raw_results)

    # 8. Sorting reading order
    ordered, t = _measure(sort_reading_order, raw_results)
    timings["sort_reading_order"] = t

    raw_text = "\n".join(text for _, text, _ in ordered)

    # 9. extract_composition_section + tokenize (matching TIDAK dijalankan di
    #    sini karena butuh database; kita hanya mengukur extract+tokenize yang
    #    seharusnya instan)
    t0 = time.perf_counter()
    section = extract_composition_section(raw_text)
    tokens = tokenize(section)
    timings["extract+tokenize"] = time.perf_counter() - t0

    total = sum(timings.values())

    return {
        "photo": photo_path.name,
        "category": photo_path.parent.name,
        "file_size_KB": round(file_size_bytes / 1024, 1),
        "resolution_orig": f"{w_orig}x{h_orig}",
        "resolution_ocr": f"{w_ocr}x{h_ocr}",
        "n_ocr_regions": n_regions,
        "n_tokens": len(tokens),
        "timings": timings,
        "total": total,
    }


def print_table(results: list[dict]) -> None:
    """Cetak tabel timing terformat ke stdout."""

    # Header metadata
    print("\n" + "=" * 130)
    print("PROFILING PIPELINE OCR — BREAKDOWN WAKTU PER TAHAP (detik)")
    print("=" * 130)

    # Kolom-kolom
    col_photo = 24
    col_stage = 10

    # Header baris 1: info foto
    header = f"{'Foto':<{col_photo}}"
    for stage in STAGE_NAMES:
        # Singkatkan nama kalau terlalu panjang
        label = stage[:col_stage]
        header += f"  {label:>{col_stage}}"
    header += f"  {'TOTAL':>{col_stage}}"
    header += f"  {'%OCR':>6}"  # persentase EasyOCR dari total
    print(header)
    print("-" * len(header))

    for r in results:
        if "error" in r:
            print(f"{r['photo']:<{col_photo}}  ERROR: {r['error']}")
            continue

        row = f"{r['photo']:<{col_photo}}"
        for stage in STAGE_NAMES:
            val = r["timings"].get(stage, 0.0)
            row += f"  {val:>{col_stage}.3f}"
        row += f"  {r['total']:>{col_stage}.3f}"

        # Persentase EasyOCR readtext dari total
        pct_ocr = (r["timings"]["easyocr_readtext"] / r["total"] * 100) if r["total"] > 0 else 0
        row += f"  {pct_ocr:>5.1f}%"
        print(row)

    # Rata-rata
    valid = [r for r in results if "error" not in r]
    if valid:
        print("-" * len(header))
        avg_row = f"{'RATA-RATA':<{col_photo}}"
        for stage in STAGE_NAMES:
            avg = sum(r["timings"].get(stage, 0) for r in valid) / len(valid)
            avg_row += f"  {avg:>{col_stage}.3f}"
        avg_total = sum(r["total"] for r in valid) / len(valid)
        avg_row += f"  {avg_total:>{col_stage}.3f}"
        avg_pct = sum(
            r["timings"]["easyocr_readtext"] / r["total"] * 100
            for r in valid
            if r["total"] > 0
        ) / len(valid)
        avg_row += f"  {avg_pct:>5.1f}%"
        print(avg_row)


def print_metadata(results: list[dict]) -> None:
    """Cetak tabel metadata (ukuran file, resolusi, jumlah region) untuk investigasi."""
    valid = [r for r in results if "error" not in r]
    if not valid:
        return

    print("\n" + "=" * 110)
    print("METADATA DIAGNOSTIK — INVESTIGASI OUTLIER")
    print("=" * 110)

    header = (
        f"{'Foto':<24}"
        f"  {'Kategori':<12}"
        f"  {'File (KB)':>10}"
        f"  {'Res. Asli':>12}"
        f"  {'Res. OCR':>12}"
        f"  {'#Region':>8}"
        f"  {'#Token':>7}"
        f"  {'Total (s)':>10}"
        f"  {'OCR (s)':>10}"
    )
    print(header)
    print("-" * len(header))

    for r in sorted(valid, key=lambda x: x["total"], reverse=True):
        line = (
            f"{r['photo']:<24}"
            f"  {r['category']:<12}"
            f"  {r['file_size_KB']:>10.1f}"
            f"  {r['resolution_orig']:>12}"
            f"  {r['resolution_ocr']:>12}"
            f"  {r['n_ocr_regions']:>8}"
            f"  {r['n_tokens']:>7}"
            f"  {r['total']:>10.3f}"
            f"  {r['timings']['easyocr_readtext']:>10.3f}"
        )
        print(line)

    # Korelasi sederhana: cari penyebab lambat
    print("\n--- ANALISIS OUTLIER ---")
    avg_total = sum(r["total"] for r in valid) / len(valid)
    outliers = [r for r in valid if r["total"] > avg_total * 2]

    if outliers:
        avg_regions_normal = sum(
            r["n_ocr_regions"] for r in valid if r not in outliers
        ) / max(len(valid) - len(outliers), 1)
        avg_filesize_normal = sum(
            r["file_size_KB"] for r in valid if r not in outliers
        ) / max(len(valid) - len(outliers), 1)

        for r in outliers:
            print(f"\n  OUTLIER: {r['photo']} ({r['total']:.1f}s, {r['total']/avg_total:.1f}x rata-rata)")
            print(f"    File size  : {r['file_size_KB']:.0f} KB  (rata-rata lain: {avg_filesize_normal:.0f} KB, "
                  f"rasio {r['file_size_KB']/avg_filesize_normal:.1f}x)")
            print(f"    #Region OCR: {r['n_ocr_regions']}  (rata-rata lain: {avg_regions_normal:.0f}, "
                  f"rasio {r['n_ocr_regions']/max(avg_regions_normal,1):.1f}x)")
            print(f"    Resolusi   : {r['resolution_orig']}  ->  {r['resolution_ocr']} (setelah downscale)")
            print(f"    Breakdown  :")
            for stage in STAGE_NAMES:
                val = r["timings"][stage]
                pct = val / r["total"] * 100 if r["total"] > 0 else 0
                bar = "█" * int(pct / 2)
                print(f"      {stage:<22} {val:>8.3f}s  ({pct:>5.1f}%)  {bar}")
    else:
        print("  Tidak ada outlier signifikan (semua foto < 2x rata-rata).")


def main():
    print("=" * 70)
    print("Profiling Pipeline OCR — Tahap Pengukuran")
    print("TIDAK ada optimasi, murni pencatatan waktu.")
    print("=" * 70)

    # Validasi semua file ada sebelum mulai (supaya tidak gagal di tengah)
    missing = []
    for category, filename in SAMPLE_PHOTOS:
        p = RAW_PHOTOS_DIR / category / filename
        if not p.exists():
            missing.append(str(p))
    if missing:
        print("ERROR: file tidak ditemukan:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    # Preload EasyOCR reader (catat waktu load model terpisah)
    print("\nMemuat model EasyOCR (one-time cost, tidak dihitung per foto)...")
    t0 = time.perf_counter()
    reader = get_reader()
    model_load_time = time.perf_counter() - t0
    print(f"Model EasyOCR dimuat dalam {model_load_time:.1f} detik.\n")

    # Profil tiap foto
    results: list[dict] = []
    for i, (category, filename) in enumerate(SAMPLE_PHOTOS, 1):
        photo_path = RAW_PHOTOS_DIR / category / filename
        print(f"[{i}/{len(SAMPLE_PHOTOS)}] Profiling {category}/{filename} ...")
        result = profile_single(photo_path, reader)
        results.append(result)
        if "error" not in result:
            print(f"         Total: {result['total']:.3f}s  |  OCR: {result['timings']['easyocr_readtext']:.3f}s  "
                  f"|  #region: {result['n_ocr_regions']}")

    # Cetak tabel hasil
    print_table(results)
    print_metadata(results)

    print(f"\nWaktu load model EasyOCR (one-time): {model_load_time:.1f}s")
    print("Selesai. Tidak ada file yang diubah.\n")


if __name__ == "__main__":
    main()
