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


if __name__ == "__main__":
    test_verdict()
    test_unmatched_tidak_dibuang()
    print("ok")
