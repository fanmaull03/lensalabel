"""Uji alur lengkap Tahap 4 -> Tahap 5 pada hasil OCR yang sudah dikumpulkan.

Alur per file: extract_composition_section() -> tokenize() -> match_token().

Token unmatched tetap ditampilkan beserta skor tertinggi yang dicapai dan
variant terdekatnya, supaya kelihatan seberapa jauh token gagal cocok dari
threshold (bahan pertimbangan kalibrasi di Tahap 9).

Jalankan dari folder backend/:
  python -m app.matching.run_matching_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.matching.fuzzy_matcher import THRESHOLD, load_knowledge_base, match_token
from app.tokenizer.tokenizer import extract_composition_section, tokenize

# Teks OCR sering berisi unicode aneh; paksa stdout UTF-8 (console Windows cp1252).
sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[3]
OCR_DIR = REPO_ROOT / "dataset" / "debug_output" / "ocr_comparison"


def main() -> None:
    files = sorted(f for f in OCR_DIR.glob("*.txt") if f.name != "_summary.txt")
    if not files:
        print(f"Tidak ada teks OCR di {OCR_DIR}. Jalankan run_ocr_comparison dulu.")
        return

    with SessionLocal() as session:
        knowledge_base = load_knowledge_base(session)

    if not knowledge_base:
        print("Knowledge base kosong. Jalankan seed_knowledge_base dulu.")
        return

    print(f"Knowledge base: {len(knowledge_base)} name_variant | threshold={THRESHOLD}")

    total_matched = total_token = 0
    for txt in files:
        tokens = tokenize(extract_composition_section(txt.read_text(encoding="utf-8")))
        results = [match_token(tok, knowledge_base) for tok in tokens]
        matched = sum(r.matched for r in results)
        total_matched += matched
        total_token += len(results)

        print(f"\n=== {txt.name} ({matched}/{len(results)} token cocok) ===")
        for r in results:
            if r.matched:
                print(
                    f"  [OK   {r.score:5.1f}] window={r.matched_window!r}\n"
                    f"      -> {r.standard_name} ({r.category}) via {r.matched_variant!r}\n"
                    f"      token: {r.token!r}"
                )
            else:
                print(
                    f"  [MISS {r.score:5.1f}] {r.token!r}\n"
                    f"      terdekat: {r.matched_variant!r} (window={r.matched_window!r})"
                )

    print(f"\n=== TOTAL: {total_matched}/{total_token} token cocok ===")


if __name__ == "__main__":
    main()
