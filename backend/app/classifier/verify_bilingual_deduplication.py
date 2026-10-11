import sys
from pathlib import Path
import cv2, easyocr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, tokenize
from app.matching.fuzzy_matcher import load_knowledge_base, match_token
from app.classifier.rule_based import classify_product
from app.db.session import SessionLocal

def main():
    reader = easyocr.Reader(["id", "en"], gpu=False)

    with SessionLocal() as session:
        knowledge_base = load_knowledge_base(session)

    p_path = REPO_ROOT / "dataset" / "raw_photos" / "melengkung" / "melengkung_005.jpeg"
    img = cv2.imread(str(p_path))
    prep = preprocess(img)
    ocr_img = _downscale(prep, MAX_OCR_WIDTH)
    raw = reader.readtext(ocr_img, detail=1)

    ordered = sort_reading_order(raw, alpha=0.8)
    raw_text = "\n".join(t for _, t, _ in ordered)
    comp_text = extract_composition_section(raw_text)
    tokens = tokenize(comp_text)
    matches = [match_token(tok, knowledge_base) for tok in tokens]

    print("==================================================================")
    print("VERIFIKASI MANUAL DEDUPLIKASI RINCIAN BAHAN: melengkung_005.jpeg")
    print("==================================================================")
    print("\n--- TOKEN MATCHING MENTAH (Sebelum Deduplikasi) ---")
    matched_std_names = []
    for tok, m in zip(tokens, matches):
        if m.matched:
            matched_std_names.append(m.standard_name)
            print(f"  [MATCH] Token: {tok!r}")
            print(f"          -> Bahan Kanonis: {m.standard_name!r} ({m.category}) | Window: {m.matched_window!r} | Skor: {m.score:.1f}")
        else:
            print(f"  [UNMATCHED] Token: {tok!r} -> terdekat: {m.matched_variant!r} (skor: {m.score:.1f})")

    print(f"\nTotal match mentah: {len(matched_std_names)} match ({matched_std_names})")

    hasil = classify_product(matches)

    print("\n==================================================================")
    print("HASIL AKHIR RINCIAN BAHAN & VERDICT (Setelah Deduplikasi)")
    print("==================================================================")
    print(f"Verdict Produk: {hasil['verdict'].upper()}")
    print(f"Badge Summary Counts: Aman={len(hasil['aman'])}, Perhatian={len(hasil['perhatian'])}, Hindari={len(hasil['hindari'])}, Tidak Dikenali={len(hasil['tidak_dikenali'])}")

    for cat in ["hindari", "perhatian", "aman"]:
        items = hasil[cat]
        print(f"\n[Kategori {cat.upper()}] ({len(items)} bahan)")
        for item in items:
            print(f"  • {item['standard_name']} (Skor Tertinggi: {item['score']:.1f})")
            print(f"    Terbaca: \"{item['matched_window']}\"")

    print(f"\n[Kategori TIDAK DIKENALI] ({len(hasil['tidak_dikenali'])} token)")
    for u in hasil["tidak_dikenali"]:
        print(f"  ? {u['token']!r} (terdekat: {u['terdekat']!r}, skor: {u['score']:.1f})")

if __name__ == "__main__":
    main()
