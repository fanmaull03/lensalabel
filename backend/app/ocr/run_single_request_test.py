"""Uji toleransi SATU request OCR di max_width=2000 pada laptop RAM terbatas.

Beda dari run_resolution_ablation.py: ini bukan batch, cuma satu foto, dan
sengaja TETAP LANJUT walau RAM bebas < 4GB (cuma kasih peringatan), karena
yang diuji justru apakah single request muat di kondisi RAM apa adanya.

Penggunaan RAM dipantau tiap 5 detik di thread terpisah, supaya kelihatan
prosesnya masih jalan atau sudah macet.

Jalankan dari folder backend/:
  python -m app.ocr.run_single_request_test
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import psutil

# Teks OCR sering berisi unicode aneh; paksa UTF-8 agar tak crash di cp1252.
sys.stdout.reconfigure(encoding="utf-8")

from app.ocr.reader import MAX_OCR_WIDTH, extract_text
from app.ocr.run_ocr_comparison import variant_b  # gray+blur+CLAHE+deskew, skip threshold
from app.ocr.run_resolution_ablation import check_ram  # reuse, jangan duplikasi

REPO_ROOT = Path(__file__).resolve().parents[3]
PHOTO = REPO_ROOT / "dataset" / "raw_photos" / "curved" / "curved_001.jpeg"
OUT_FILE = REPO_ROOT / "dataset" / "debug_output" / "single_request_test.txt"
MONITOR_INTERVAL = 5  # detik

peak_rss_gb = 0.0  # puncak RAM sungguhan; RSS di akhir sudah turun, bukan puncak


def monitor_ram(stop: threading.Event, start: float) -> None:
    """Print pemakaian RAM tiap MONITOR_INTERVAL detik sampai stop di-set."""
    global peak_rss_gb
    process = psutil.Process()
    while not stop.wait(MONITOR_INTERVAL):
        mem = psutil.virtual_memory()
        rss_gb = process.memory_info().rss / 1e9
        peak_rss_gb = max(peak_rss_gb, rss_gb)
        print(
            f"  [{time.perf_counter() - start:5.0f}s] proses ini: {rss_gb:.2f} GB | "
            f"RAM bebas: {mem.available / 1e9:.2f} GB ({mem.percent:.0f}% terpakai)",
            flush=True,
        )


def main() -> None:
    check_ram()  # peringatan saja, tetap lanjut (beda dari batch test)

    image = cv2.imread(str(PHOTO))
    if image is None:
        print(f"Gagal baca foto: {PHOTO}")
        return

    h, w = image.shape[:2]
    print(f"\nFoto   : {PHOTO.name} ({w}x{h}, {w * h / 1e6:.1f} MP)")
    print(f"Target : varian B (gray+blur+CLAHE+deskew, SKIP threshold) + OCR @ max_width={MAX_OCR_WIDTH}")
    print(f"Mulai  : {datetime.now():%H:%M:%S}\n")

    start = time.perf_counter()
    stop = threading.Event()
    threading.Thread(target=monitor_ram, args=(stop, start), daemon=True).start()

    try:
        processed = variant_b(image)
        print(f"  [{time.perf_counter() - start:5.0f}s] preprocessing selesai, mulai OCR ...", flush=True)
        text = extract_text(processed)  # pakai default MAX_OCR_WIDTH yang baru
    finally:
        stop.set()

    elapsed = time.perf_counter() - start
    OUT_FILE.write_text(text, encoding="utf-8")  # simpan dulu, jangan sampai hilang

    print(f"\nSelesai: {datetime.now():%H:%M:%S} | total {elapsed:.1f} detik")
    print(f"Puncak RAM proses: {peak_rss_gb:.2f} GB (sampling tiap {MONITOR_INTERVAL}s)")
    print(f"Hasil OCR ({len(text)} karakter) disimpan ke {OUT_FILE}:\n{text}")


if __name__ == "__main__":
    main()
