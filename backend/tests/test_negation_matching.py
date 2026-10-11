"""Regression tests for local negation handling in fuzzy matching."""

from app.matching.fuzzy_matcher import match_token

KB = [
    {"ingredient_id": 1, "standard_name": "Gluten", "category": "hindari", "name_variant": "Gluten"},
    {"ingredient_id": 2, "standard_name": "Laktosa", "category": "perhatian", "name_variant": "Laktosa"},
    {"ingredient_id": 3, "standard_name": "Susu", "category": "hindari", "name_variant": "Susu"},
    {"ingredient_id": 4, "standard_name": "Kasein", "category": "hindari", "name_variant": "Kasein"},
    {"ingredient_id": 5, "standard_name": "Kacang Tanah", "category": "hindari", "name_variant": "Kacang Tanah"},
    {"ingredient_id": 6, "standard_name": "Tepung terigu", "category": "hindari", "name_variant": "Wheat flour"},
]


def matched(token: str, variant: str) -> bool:
    result = match_token(token, [entry for entry in KB if entry["name_variant"] == variant])
    return result.matched


def test_negated_and_positive_indonesian_forms():
    assert not matched("Tepung Bebas Gluten", "Gluten")
    assert not matched("Tepung Bebas dari Gluten", "Gluten")
    assert not matched("Tepung Tanpa Gluten", "Gluten")
    assert not matched("Tepung Non-Gluten Flour", "Gluten")
    assert not matched("Tepung 0% Gluten", "Gluten")
    assert not matched("Tepung Tidak Mengandung Gluten", "Gluten")
    assert matched("Tepung Mengandung Gluten", "Gluten")


def test_english_free_forms():
    assert not matched("Gluten-Free Flour", "Gluten")
    assert not matched("Gluten free flour", "Gluten")


def test_qualifier_does_not_spread_to_other_ingredients():
    assert not matched("Susu Bebas Laktosa", "Laktosa")
    assert matched("Susu Bebas Laktosa", "Susu")
    assert matched("Kasein", "Kasein")
    assert matched("Kacang Tanah", "Kacang Tanah")


def test_mixed_negated_and_positive_clauses():
    assert not matched("Bebas Gula", "Gluten")
    assert matched("Mengandung Gluten", "Gluten")
    assert not matched("Bebas Gluten", "Gluten")
    assert matched("Mengandung Susu", "Susu")


def test_zero_percent_requires_an_intact_unit_immediately_before_target():
    assert matched("Wheat flour (56%)", "Wheat flour")
    assert matched("susu skim bubuk (1.46%)", "Susu")
    assert matched("Penstabil (...) INGREDIENTS 0 Wheat flour (56%)", "Wheat flour")
    assert not matched("0% Gluten", "Gluten")
    assert not matched("Mengandung 0% Susu", "Susu")
    assert not matched("Mengandung 0 % Susu", "Susu")
    assert not matched("Mengandung 0.0% Susu", "Susu")
    assert not matched("Mengandung 0,0% Susu", "Susu")


if __name__ == "__main__":
    test_negated_and_positive_indonesian_forms()
    test_english_free_forms()
    test_qualifier_does_not_spread_to_other_ingredients()
    test_mixed_negated_and_positive_clauses()
    test_zero_percent_requires_an_intact_unit_immediately_before_target()
    print("ok")
