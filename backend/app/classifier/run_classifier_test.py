"""Uji Tahap 4 -> 5 -> 6 pada teks OCR yang sudah ada, plus 2 kasus uji manual.

Alur per file: extract_composition_section() -> tokenize() -> match_token()
untuk semua token -> classify_product().

Jalankan dari folder backend/:
  python -m app.classifier.run_classifier_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.classifier.rule_based import CATEGORIES, UNKNOWN_GROUP, classify_product
from app.matching.fuzzy_matcher import MatchResult, load_knowledge_base, match_token
from app.tokenizer.tokenizer import extract_composition_section, tokenize

# Teks OCR sering berisi unicode aneh; paksa stdout UTF-8 (console Windows cp1252).
sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[3]
OCR_DIR = REPO_ROOT / "dataset" / "debug_output" / "ocr_comparison"
SAMPLE_SIZE = 5  # cukup untuk melihat pola, tidak perlu semua file


def print_report(judul: str, hasil: dict) -> None:
    print(f"\n=== {judul} ===")
    print(f"  VERDICT: {hasil['verdict'].upper()}")
    for cat in CATEGORIES:
        bahan = hasil[cat]
        print(f"  [{cat}] {len(bahan)} bahan")
        for b in bahan:
            print(
                f"      - {b['standard_name']:22} "
                f"(skor {b['score']:5.1f} dari {b['matched_window']!r})"
            )
    unknown = hasil[UNKNOWN_GROUP]
    print(f"  [{UNKNOWN_GROUP}] {len(unknown)} token")
    for u in unknown:
        print(f"      ? {u['token'][:70]!r} (skor {u['score']:5.1f})")


def kasus_uji_manual() -> None:
    """Dua false positive yang sudah dikonfirmasi manual di Tahap 5.

    Data palsu, BUKAN dari OCR. Tujuannya mendokumentasikan bahwa verdict akhir
    ikut salah kalau false positive matching tidak ditangani. Belum diperbaiki
    di sini; ini bahan kalibrasi Tahap 9 (bobot + threshold + penalti untuk
    name_variant pendek).
    """
    # Kasus 1: window 'Cocok' (potongan kalimat "Cocok dikonsumsi") match ke
    # Cokelat lewat variant 'Cocoa', skor 82.3. Produk yang sebenarnya cuma
    # berisi bahan aman jadi ikut ter-flag 'perhatian'.
    kasus_cocok = [
        MatchResult(
            token="Air Garam",
            matched=True,
            score=100.0,
            matched_window="Garam",
            matched_variant="Garam",
            ingredient_id=1,
            standard_name="Garam",
            category="aman",
        ),
        MatchResult(
            token="Perhatikan Cocok dikonsumsi sebelum tanggal",
            matched=True,
            score=82.3,
            matched_window="Cocok",
            matched_variant="Cocoa",
            ingredient_id=2,
            standard_name="Cokelat",
            category="perhatian",
        ),
    ]
    print_report(
        "KASUS UJI MANUAL 1 - false positive 'Cocok' -> Cokelat",
        classify_product(kasus_cocok),
    )
    print("  CATATAN: 'Cocok' itu kata Indonesia biasa dari kalimat 'Cocok")
    print("  dikonsumsi', bukan cocoa. Verdict SEHARUSNYA 'aman', bukan 'perhatian'.")

    # Kasus 2: window 'Vitamin' match ke Asam askorbat lewat variant 'vitamin C',
    # skor 89.6. Vitamin generik bisa A/D/E; sistem mengaku tahu padahal tidak,
    # dan produk langsung disimpulkan 'aman' tanpa perlu verifikasi.
    kasus_vitamin = [
        MatchResult(
            token="Vitamin Perisa Sintetik",
            matched=True,
            score=89.6,
            matched_window="Vitamin",
            matched_variant="vitamin C",
            ingredient_id=3,
            standard_name="Asam askorbat",
            category="aman",
        ),
    ]
    print_report(
        "KASUS UJI MANUAL 2 - false positive 'Vitamin' -> Asam askorbat",
        classify_product(kasus_vitamin),
    )
    print("  CATATAN: 'Vitamin' generik belum tentu vitamin C, dan token aslinya")
    print("  juga memuat 'Perisa Sintetik' yang tidak ke-match. Verdict SEHARUSNYA")
    print("  'perlu_verifikasi', bukan 'aman'.")

    # Kasus 3: aturan 0. Foto gagal dibaca, tokenizer tidak menghasilkan token
    # sama sekali, sehingga match_token() tidak pernah dipanggil.
    print_report("KASUS UJI MANUAL 3 - matches kosong (aturan 0)", classify_product([]))
    print("  CATATAN: bukan 'aman' (tidak ada bukti apa pun) dan bukan juga")
    print("  'perlu_verifikasi' (tidak ada satu pun bahan yang terbaca).")

    # Kasus 4: 'Salt' match ke Barley lewat sinonim 'malt', skor 75.0 (persis di
    # THRESHOLD). Ditemukan lewat uji end-to-end di frontend pakai foto
    # normal_003.jpeg: verdict keluar 'hindari' padahal garam itu bahan aman.
    # 'Salt' dan 'malt' beda satu huruf tapi maknanya bertolak belakang; satu
    # bahan aman, satu sumber gluten. Ini false positive paling berbahaya dari
    # ketiganya karena arah salahnya ke 'hindari': produk yang sebenarnya boleh
    # dimakan jadi ditolak.
    #
    # BUKAN untuk diperbaiki sekarang. Dokumentasi supaya divalidasi ulang
    # setelah penalti panjang kata diterapkan di Tahap 9. Lihat juga assert di
    # tests/test_fuzzy_matcher.py yang mengunci angkanya.
    kasus_salt = [
        MatchResult(
            token="Wheat Flour Sugar Salt",
            matched=True,
            score=100.0,
            matched_window="Wheat Flour",
            matched_variant="Wheat flour",
            ingredient_id=4,
            standard_name="Tepung terigu",
            category="hindari",
        ),
        MatchResult(
            token="Salt",
            matched=True,
            score=75.0,
            matched_window="Salt",
            matched_variant="malt",
            ingredient_id=5,
            standard_name="Barley",
            category="hindari",
        ),
    ]
    hasil_salt = classify_product(kasus_salt)
    print_report("KASUS UJI MANUAL 4 - false positive 'Salt' -> Barley via 'malt'", hasil_salt)
    assert hasil_salt["verdict"] == "hindari", "kasus 4 seharusnya menghasilkan verdict salah"
    print("  CATATAN: 'Salt' = garam (bahan aman), bukan 'malt' (sumber gluten).")
    print("  Barley TIDAK seharusnya muncul di daftar hindari. Di foto normal_003")
    print("  ini bikin seluruh produk ter-vonis 'hindari' secara keliru.")
    print("  Akar masalah ganda: (a) skor 75.0 persis di THRESHOLD, (b) 'salt'")
    print("  belum ada sebagai sinonim Garam di knowledge base, jadi tidak ada")
    print("  kandidat benar yang bisa mengalahkan 'malt'.")


def main() -> None:
    files = sorted(f for f in OCR_DIR.glob("*.txt") if f.name != "_summary.txt")
    if not files:
        print(f"Tidak ada teks OCR di {OCR_DIR}. Jalankan run_ocr_comparison dulu.")
        return

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        knowledge_base = load_knowledge_base(session)

    if not knowledge_base:
        print("Knowledge base kosong. Jalankan seed_knowledge_base dulu.")
        return

    print(f"Knowledge base: {len(knowledge_base)} name_variant")
    for txt in files[:SAMPLE_SIZE]:
        tokens = tokenize(extract_composition_section(txt.read_text(encoding="utf-8")))
        matches = [match_token(tok, knowledge_base) for tok in tokens]
        print_report(txt.name, classify_product(matches))

    kasus_uji_manual()


if __name__ == "__main__":
    main()
