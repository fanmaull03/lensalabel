"""Pengujian Fuzzy Matcher - Length Penalty & Tie Boundary Decision.

Menguji penalti selisih panjang karakter (Issue 1) dan keputusan batas pas threshold
(Issue 2).
"""

from app.matching.fuzzy_matcher import THRESHOLD, MatchResult, composite_score, match_token

# Mock KB sederhana untuk pengujian terisolasi tanpa koneksi DB
MOCK_KB = [
    {
        "ingredient_id": 1,
        "standard_name": "Cokelat",
        "category": "perhatian",
        "name_variant": "Cokelat",
    },
    {
        "ingredient_id": 2,
        "standard_name": "Asam askorbat",
        "category": "aman",
        "name_variant": "Asam askorbat",
    },
    {
        "ingredient_id": 2,
        "standard_name": "Asam askorbat",
        "category": "aman",
        "name_variant": "vitamin C",
    },
    {
        "ingredient_id": 3,
        "standard_name": "Barley",
        "category": "hindari",
        "name_variant": "Barley",
    },
    {
        "ingredient_id": 4,
        "standard_name": "Susu sapi",
        "category": "hindari",
        "name_variant": "Susu",
    },
    {
        "ingredient_id": 5,
        "standard_name": "Natrium klorida",
        "category": "aman",
        "name_variant": "Garam",
    },
]


def test_length_penalty_mencegah_false_positive_kata_pendek():
    """Issue 1: Kata pendek tidak boleh match ke target yang jauh lebih panjang."""
    # 1. "Cocok" vs "Cokelat"
    skor_cocok_cokelat = composite_score("Cocok", "Cokelat")
    assert (
        skor_cocok_cokelat < THRESHOLD
    ), f"'Cocok' vs 'Cokelat' harus < threshold ({skor_cocok_cokelat})"

    # 2. "Vitamin" vs "Asam askorbat" & "vitamin C"
    skor_vit_askorbat = composite_score("Vitamin", "Asam askorbat")
    assert (
        skor_vit_askorbat < THRESHOLD
    ), f"'Vitamin' vs 'Asam askorbat' harus < threshold ({skor_vit_askorbat})"

    skor_vit_c = composite_score("Vitamin", "vitamin C")
    assert (
        skor_vit_c < THRESHOLD
    ), f"'Vitamin' vs 'vitamin C' harus < threshold ({skor_vit_c})"

    # 3. "Salt" vs "Barley"
    skor_salt_barley = composite_score("Salt", "Barley")
    assert (
        skor_salt_barley < THRESHOLD
    ), f"'Salt' vs 'Barley' harus < threshold ({skor_salt_barley})"


def test_valid_matches_tetap_lolos_tanpa_regresi():
    """Issue 1: Token yang valid & typo minor harus tetap match."""
    # Kapitalisasi berbeda
    assert composite_score("Susu", "susu") >= THRESHOLD

    # Typo minor 1 karakter
    assert composite_score("Susu", "Susuu") >= THRESHOLD
    assert composite_score("Pemanis", "Pemaniss") >= THRESHOLD
    assert composite_score("Garam", "Garam") >= THRESHOLD


def test_tie_boundary_exact_threshold():
    """Issue 2: Skor yang PERSIS SAMA DENGAN threshold (75.0 == 75.0) HARUS dianggap MATCH."""
    # Uji eksplisit match_token dengan threshold yang disetel sama persis dengan composite_score
    raw_score = composite_score("Salt", "malt")  # persis 75.0
    assert raw_score == 75.0, f"Skor Salt vs malt diharapkan 75.0, dapat {raw_score}"

    # Jalankan match_token dengan threshold 75.0
    mock_kb_malt = [
        {
            "ingredient_id": 99,
            "standard_name": "Barley",
            "category": "hindari",
            "name_variant": "malt",
        }
    ]
    result: MatchResult = match_token("Salt", mock_kb_malt, threshold=75.0)

    # Pastikan skor pas di 75.0 dianggap MATCH (matched == True, operator >=)
    assert result.score == 75.0
    assert (
        result.matched is True
    ), "Skor yang tepat sama dengan threshold (75.0 == 75.0) harus dianggap MATCH (>=)"


def test_length_penalty_exponent_is_configurable_and_default_is_unchanged():
    default_score = composite_score("Susu", "Susu sapi")
    explicit_default_score = composite_score("Susu", "Susu sapi", length_penalty_exponent=0.8)
    no_penalty_score = composite_score("Susu", "Susu sapi", length_penalty_exponent=0.0)
    assert default_score == explicit_default_score
    assert no_penalty_score > default_score


if __name__ == "__main__":
    test_length_penalty_mencegah_false_positive_kata_pendek()
    test_valid_matches_tetap_lolos_tanpa_regresi()
    test_tie_boundary_exact_threshold()
    print("ALL FUZZY MATCHER TESTS PASSED!")
