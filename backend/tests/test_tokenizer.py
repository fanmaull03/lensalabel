"""Regression tests for composition closing-marker detection.

Run from backend/:
  python -m tests.test_tokenizer
  pytest tests/test_tokenizer.py
"""

from app.tokenizer.tokenizer import extract_composition_section


def test_ingredient_word_does_not_close_composition():
    text = (
        "Komposisi: Tepung Terigu, Minyak Sawit [mengandung Antioksidan TBHQ (E319)], "
        "Perisa Sintetik Ayam [mengandung Telur, Susu, dan Kedelai], Garam."
    )
    assert extract_composition_section(text) == text


def test_allergen_disclaimer_closes_composition():
    text = (
        "Komposisi: Tepung Terigu, Susu Bubuk, Garam.\n"
        "Mengandung alergen, lihat daftar bahan yang dicetak tebal.\n"
        "Diproduksi dengan peralatan yang juga memproses produk yang mengandung kacang."
    )
    assert extract_composition_section(text) == "Komposisi: Tepung Terigu, Susu Bubuk, Garam."


def test_allergen_disclaimer_variant_closes_composition():
    text = (
        "Komposisi: Tepung Terigu, Garam.\n"
        "Mengandung Telur, Susu, dan Kedelai, lihat daftar bahan yang dicetak tebal."
    )
    assert extract_composition_section(text) == "Komposisi: Tepung Terigu, Garam."


def test_sweetener_warning_disclaimer_closes_composition():
    text = (
        "Komposisi: Gula Pasir (mengandung pengawet sulfit), Air, Perisa Sintetik Melon, "
        "Pengatur Keasaman Asam Sitrat, Pemanis Buatan Sukralosa, Pewarna Sintetik "
        "(Tartrazine CI 19140, Biru Berlian CI 42090).\n"
        "Mengandung pemanis buatan, disarankan tidak dikonsumsi oleh anak-anak di bawah "
        "5(lima) tahun, ibu hamil, dan ibu menyusui."
    )
    expected = (
        "Komposisi: Gula Pasir (mengandung pengawet sulfit), Air, Perisa Sintetik Melon, "
        "Pengatur Keasaman Asam Sitrat, Pemanis Buatan Sukralosa, Pewarna Sintetik "
        "(Tartrazine CI 19140, Biru Berlian CI 42090)."
    )
    assert extract_composition_section(text) == expected


def test_product_word_does_not_close_composition():
    text = "Komposisi: Ekstrak Ragi, Produk Fermentasi Kedelai, Garam, Gula."
    assert extract_composition_section(text) == text


def test_production_code_closes_composition():
    text = "Komposisi: Gula, Garam, Perisa Sintetik.\nKode Produksi: Lihat Kemasan."
    assert extract_composition_section(text) == "Komposisi: Gula, Garam, Perisa Sintetik."


def test_contextual_production_markers_are_valid():
    for marker in ("Diproduksi oleh", "Diproduksi di", "Diproduksi dengan"):
        text = f"Komposisi: Gula, Garam.\n{marker} fasilitas lain."
        assert extract_composition_section(text) == "Komposisi: Gula, Garam."


if __name__ == "__main__":
    test_ingredient_word_does_not_close_composition()
    test_allergen_disclaimer_closes_composition()
    test_allergen_disclaimer_variant_closes_composition()
    test_sweetener_warning_disclaimer_closes_composition()
    test_product_word_does_not_close_composition()
    test_production_code_closes_composition()
    test_contextual_production_markers_are_valid()
    print("ok")
