"""Uji alur Tahap 4 pada teks OCR mentah yang sudah dikumpulkan.

Alur: extract_composition_section() dulu (buang tabel gizi & teks lain),
baru tokenize(). Baca tiap .txt di dataset/debug_output/ocr_comparison/
(kecuali _summary.txt), print rentang yang terpotong + daftar token per file
untuk cek visual sebelum lanjut ke fuzzy matching.

Jalankan dari folder backend/:
  python -m app.tokenizer.run_tokenizer_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.tokenizer.tokenizer import extract_composition_section, tokenize

# Teks OCR sering berisi unicode aneh; paksa stdout UTF-8 agar tak crash di
# console Windows (cp1252).
sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[3]
OCR_DIR = REPO_ROOT / "dataset" / "debug_output" / "ocr_comparison"


def main() -> None:
    files = sorted(f for f in OCR_DIR.glob("*.txt") if f.name != "_summary.txt")
    if not files:
        print(f"Tidak ada teks OCR di {OCR_DIR}. Jalankan run_ocr_comparison dulu.")
        return

    for txt in files:
        raw = txt.read_text(encoding="utf-8")
        section = extract_composition_section(raw)
        tokens = tokenize(section)

        # section is raw = penanda pembuka tidak ketemu, teks dipakai utuh
        status = "TIDAK ketemu (pakai teks utuh)" if section == raw else "ketemu"
        reduksi = 100 - (len(section) / len(raw) * 100) if raw else 0

        print(f"\n=== {txt.name} ({len(tokens)} token) ===")
        print(f"  penanda komposisi: {status} | {len(raw)} -> {len(section)} char "
              f"(-{reduksi:.0f}%)")
        for i, tok in enumerate(tokens, 1):
            print(f"  {i:2}. {tok}")


if __name__ == "__main__":
    main()
