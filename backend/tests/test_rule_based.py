"""Cek 4 aturan verdict classify_product() (Tahap 6).

  python -m tests.test_rule_based    (atau: pytest tests/test_rule_based.py)
"""

from app.classifier.rule_based import UNKNOWN_GROUP, classify_product
from app.matching.fuzzy_matcher import MatchResult


def _cocok(category: str) -> MatchResult:
    return MatchResult(
        token="x",
        matched=True,
        score=100.0,
        matched_window="x",
        matched_variant="x",
        ingredient_id=1,
        standard_name="X",
        category=category,
    )


def _gagal() -> MatchResult:
    return MatchResult(token="zzz", matched=False, score=40.0, matched_window="zzz")


def test_verdict():
    # 0. matches kosong -> tidak_terbaca, BUKAN aman
    assert classify_product([])["verdict"] == "tidak_terbaca"
    # 1. ada hindari -> hindari, walau ada perhatian & unmatched
    assert (
        classify_product([_cocok("hindari"), _cocok("perhatian"), _gagal()])["verdict"]
        == "hindari"
    )
    # 2. tidak ada hindari, ada perhatian -> perhatian
    assert classify_product([_cocok("aman"), _cocok("perhatian")])["verdict"] == "perhatian"
    # 3. semua aman, tanpa unmatched -> aman
    assert classify_product([_cocok("aman"), _cocok("aman")])["verdict"] == "aman"
    # 4. semua aman, ada unmatched -> perlu_verifikasi (bukan aman)
    assert classify_product([_cocok("aman"), _gagal()])["verdict"] == "perlu_verifikasi"


def test_unmatched_tidak_dibuang():
    hasil = classify_product([_cocok("aman"), _gagal(), _gagal()])
    assert len(hasil[UNKNOWN_GROUP]) == 2
    assert len(hasil["aman"]) == 1


def test_deduplication_bilingual_same_canonical_ingredient():
    """Token bilingual yang cocok ke bahan kanonis yang sama harus dideduplikasi.

    Misal: 'Susu Sapi Segar' dan 'Fresh Milk' keduanya match ke kanonis 'Susu sapi'.
    Harus menghasilkan 1 baris di kategori 'hindari' dengan matched_window gabungan.
    """
    match_id = MatchResult(
        token="Susu Sapi Segar (99.8%)",
        matched=True,
        score=98.0,
        matched_window="Susu Sapi Segar",
        matched_variant="Susu sapi",
        ingredient_id=3,
        standard_name="Susu sapi",
        category="hindari",
    )
    match_en = MatchResult(
        token="Fresh Milk (51.8%)",
        matched=True,
        score=95.0,
        matched_window="Fresh Milk",
        matched_variant="Fresh milk",
        ingredient_id=3,
        standard_name="Susu sapi",
        category="hindari",
    )
    match_sugar = MatchResult(
        token="Gula",
        matched=True,
        score=100.0,
        matched_window="Gula",
        matched_variant="Gula",
        ingredient_id=10,
        standard_name="Gula",
        category="aman",
    )

    hasil = classify_product([match_id, match_en, match_sugar])

    # Harus dihitung 1 bahan hindari, bukan 2
    assert len(hasil["hindari"]) == 1
    assert len(hasil["aman"]) == 1
    assert hasil["verdict"] == "hindari"

    susu_entry = hasil["hindari"][0]
    assert susu_entry["standard_name"] == "Susu sapi"
    assert susu_entry["matched_window"] == "Susu Sapi Segar, Fresh Milk"
    assert susu_entry["score"] == 98.0


def test_deduplication_distinct_canonical_ingredients():
    """Bahan kanonis berbeda tetap dilaporkan sebagai baris terpisah."""
    match_susu = MatchResult(
        token="Susu",
        matched=True,
        score=100.0,
        matched_window="Susu",
        matched_variant="Susu",
        ingredient_id=3,
        standard_name="Susu sapi",
        category="hindari",
    )
    match_keju = MatchResult(
        token="Keju Cheddar",
        matched=True,
        score=95.0,
        matched_window="Keju",
        matched_variant="Keju",
        ingredient_id=4,
        standard_name="Keju",
        category="hindari",
    )
    hasil = classify_product([match_susu, match_keju])

    assert len(hasil["hindari"]) == 2
    assert [b["standard_name"] for b in hasil["hindari"]] == ["Susu sapi", "Keju"]


if __name__ == "__main__":
    test_verdict()
    test_unmatched_tidak_dibuang()
    test_deduplication_bilingual_same_canonical_ingredient()
    test_deduplication_distinct_canonical_ingredients()
    print("ok")

