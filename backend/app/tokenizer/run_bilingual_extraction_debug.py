"""Debug extract_composition_section() dengan tiga pola label bilingual sintetis.

Jalankan dari folder backend/:
  python -m app.tokenizer.run_bilingual_extraction_debug

Script ini hanya membaca fungsi tokenizer yang ada; tidak mengubah pipeline,
dataset, ground truth, atau evaluator.
"""

from rapidfuzz import fuzz

from app.tokenizer.tokenizer import CLOSE_MARKERS, extract_composition_section


EXAMPLES = {
    "Pola 1 - KOMPOSISI lalu INGREDIENTS": """KOMPOSISI : Tepung Terigu, Minyak Sawit, Garam.
INGREDIENTS : Wheat Flour, Palm Oil, Salt.
Allergen Information: contains wheat.""",
    "Pola 2 - INGREDIENTS lalu KOMPOSISI": """Ingredients: Sunflower Seeds, Salt, Sugar, Garlic Powder.
Komposisi: Biji Bunga Matahari, Garam, Gula, Bubuk Bawang Putih.
Kode Produksi: Lihat Kemasan.""",
    "Pola 3 - marker gabungan": """KOMPOSISI / INGREDIENTS

Cokelat Pasta (47,27%) (mengandung susu), Jagung, Tepung Terigu.

Chocolate Paste (47.27%) (contains milk), Corn, Wheat Flour.

- Mengandung alergen pada huruf yang dicetak tebal.""",
    "Test A - mengandung di tengah": """Komposisi: Tepung Terigu, Minyak Sawit [mengandung Antioksidan TBHQ (E319)], Perisa Sintetik Ayam [mengandung Telur, Susu, dan Kedelai], Garam.""",
    "Test B - disclaimer alergen": """Komposisi: Tepung Terigu, Susu Bubuk, Garam.
Mengandung alergen, lihat daftar bahan yang dicetak tebal.
Diproduksi dengan peralatan yang juga memproses produk yang mengandung kacang.""",
    "Test C - produk di tengah": """Komposisi: Ekstrak Ragi, Produk Fermentasi Kedelai, Garam, Gula.""",
    "Test D - Kode Produksi": """Komposisi: Gula, Garam, Perisa Sintetik.
Kode Produksi: Lihat Kemasan.""",
}


print("=== SKOR MARKER ===")
for candidate in (
    "mengandung",
    "mengandung Antioksidan",
    "mengandung alergen",
    "produk",
    "produksi",
    "Produksi: Lihat",
    "diproduksi oleh",
    "diproduksi dengan peralatan",
):
    print(
        f"{candidate!r}: ",
        f"MENGANDUNG ALERGEN={fuzz.ratio('MENGANDUNG ALERGEN', candidate.upper()):.2f}, ",
        f"DIPRODUKSI={fuzz.ratio('DIPRODUKSI', candidate.upper()):.2f}",
    )


for label, text in EXAMPLES.items():
    print(f"\n=== {label} ===")
    print("INPUT:")
    print(text)
    print("\nHASIL extract_composition_section():")
    print(extract_composition_section(text))
