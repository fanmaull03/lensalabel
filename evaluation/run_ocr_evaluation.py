"""
Evaluasi kuantitatif OCR (dipakai di Tahap 9 CRISP-DM): Character Error Rate
(CER) dan Word Error Rate (WER) terhadap ground truth transkrip manual.

Pipeline preprocessing mengikuti proposal revisi:
    grayscale -> blur -> CLAHE -> deskew

PENTING soal ground truth (transcripts.csv):
- Kolom ground_truth_text harus teks komposisi POLOS saja, tanpa markup
  apa pun untuk bahan yang dicetak tebal (bold) di kemasan. Konvensi
  penandaan alergen bold itu urusan evaluasi Precision/Recall/F1 di tahap
  fuzzy matching nanti, BUKAN bagian dari perhitungan CER/WER di sini.
  Kalau ground truth ikut menyisipkan tanda markup, angka CER/WER akan
  salah karena dibandingkan ke output OCR yang tidak pernah punya markup.

Cara pakai (dari root folder project, bukan dari dalam backend/):
  pip install jiwer
  isi dataset/ground_truth/transcripts.csv (lihat template kolom di bawah)
  python evaluation/run_ocr_evaluation.py
"""

from __future__ import annotations

import csv
import datetime
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import jiwer

# Reuse modul dari backend/app tanpa duplikasi logika. Script ini sengaja
# ditaruh di evaluation/ (di luar backend/) karena sifatnya riset CRISP-DM,
# bukan kode produksi, jadi path backend perlu ditambahkan manual.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.preprocessing.pipeline import (  # noqa: E402
    to_grayscale,
    reduce_noise,
    enhance_contrast,
    deskew,
)
from app.ocr.reader import extract_text  # noqa: E402

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
GROUND_TRUTH_CSV = DATASET_DIR / "ground_truth" / "transcripts.csv"
RAW_PHOTOS_DIR = DATASET_DIR / "raw_photos"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

def run_pipeline(image):
    """Jalankan empat tahap preprocessing sesuai proposal revisi."""
    gray = to_grayscale(image)
    blurred = reduce_noise(gray)
    contrast = enhance_contrast(blurred)
    return deskew(contrast)


def load_ground_truth() -> list[dict]:
    if not GROUND_TRUTH_CSV.exists():
        print(f"Belum ada {GROUND_TRUTH_CSV}. Buat dulu filenya, kolom minimal:")
        print("filename,category,ground_truth_text")
        return []

    with open(GROUND_TRUTH_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"{GROUND_TRUTH_CSV} masih kosong, isi ground truth-nya dulu.")
    return rows


def evaluate() -> None:
    rows = load_ground_truth()
    if not rows:
        return

    per_photo_results = []

    for row in rows:
        filename = row["filename"]
        category = row["category"]
        ground_truth = row["ground_truth_text"]

        image_path = RAW_PHOTOS_DIR / category / filename
        if not image_path.exists():
            print(f"lewati, file tidak ditemukan: {image_path}")
            continue

        image = cv2.imread(str(image_path))
        if image is None:
            print(f"lewati, gagal dibaca cv2: {image_path}")
            continue

        processed = run_pipeline(image)
        hypothesis = extract_text(processed)

        cer = jiwer.cer(ground_truth, hypothesis)
        wer = jiwer.wer(ground_truth, hypothesis)

        per_photo_results.append(
            {
                "filename": filename,
                "category": category,
                "cer": round(cer, 4),
                "wer": round(wer, 4),
            }
        )
        print(f"{filename:<20} CER={cer:.4f} WER={wer:.4f}")

    if not per_photo_results:
        print("Tidak ada foto yang berhasil dievaluasi, cek path dan ground truth.")
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    detail_path = RESULTS_DIR / f"ocr_evaluation_{timestamp}.csv"
    with open(detail_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "category", "cer", "wer"])
        writer.writeheader()
        writer.writerows(per_photo_results)

    summarize(per_photo_results)
    print(f"\nDetail per foto disimpan ke {detail_path}")


def summarize(results: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        groups[r["category"]].append(r)

    summary_rows = []
    for category, items in sorted(groups.items()):
        avg_cer = sum(i["cer"] for i in items) / len(items)
        avg_wer = sum(i["wer"] for i in items) / len(items)
        summary_rows.append(
            {
                "category": category,
                "n_foto": len(items),
                "avg_cer": round(avg_cer, 4),
                "avg_wer": round(avg_wer, 4),
            }
        )

    summary_path = RESULTS_DIR / "ocr_evaluation_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["category", "n_foto", "avg_cer", "avg_wer"]
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n=== RINGKASAN PER KATEGORI (rata-rata CER/WER) ===")
    print(f"{'kategori':<16}{'n':<5}{'avg CER':<10}{'avg WER':<10}")
    for row in summary_rows:
        print(
            f"{row['category']:<16}{row['n_foto']:<5}"
            f"{row['avg_cer']:<10}{row['avg_wer']:<10}"
        )
    print(f"\nRingkasan disimpan ke {summary_path}")


if __name__ == "__main__":
    evaluate()
