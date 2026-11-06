"""Cetak daftar lengkap Ground Truth Anotasi Bahan untuk 40 Foto Kalibrasi."""

import json
from pathlib import Path

GT_FILE = Path(__file__).resolve().parent.parent / "dataset" / "ground_truth" / "calibration_ingredients_gt.json"

def main():
    if not GT_FILE.exists():
        print("File Ground Truth belum ada.")
        return

    with open(GT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 80)
    print("DAFTAR ANOTASI GROUND TRUTH BAHAN - 40 FOTO KALIBRASI (20 DATAR + 20 MELENGKUNG)")
    print("=" * 80)
    print()

    cat_counts = {"hindari": 0, "perhatian": 0, "aman": 0}

    for idx, (fn, info) in enumerate(data.items(), 1):
        print(f"[{idx:02d}/40] Foto: {fn} | Kategori: {info['category']}")
        print(f"     Teks GT : \"{info['ground_truth_text']}\"")
        ings = info["ingredients"]
        if ings:
            print("     Bahan GT Terdeteksi:")
            for ing in ings:
                cat = ing["category"].lower()
                if cat in cat_counts:
                    cat_counts[cat] += 1
                badge = f"[{ing['category'].upper():9}]"
                print(f"       • {badge} {ing['standard_name']} (cocok varian: \"{ing['matched_variant']}\")")
        else:
            print("     Bahan GT : (Tidak ada bahan KB yang cocok dalam teks komposisi)")
        print("-" * 80)

    print()
    print("= " * 40)
    print("RINGKASAN TOTAL ANOTASI BAHAN SUBSET KALIBRASI (40 FOTO):")
    print(f"  • Total Bahan HINDARI   : {cat_counts['hindari']}")
    print(f"  • Total Bahan PERHATIAN : {cat_counts['perhatian']}")
    print(f"  • Total Bahan AMAN      : {cat_counts['aman']}")
    print(f"  • Total Keseluruhan     : {sum(cat_counts.values())}")
    print("= " * 40)

if __name__ == "__main__":
    main()
