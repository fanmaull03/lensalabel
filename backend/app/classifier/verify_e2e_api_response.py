"""Verifikasi E2E deduplikasi Rincian Bahan - mereplikasi PERSIS logika
endpoint POST /identify (_classify_text di routes_identify.py), termasuk
output JSON IdentifyResponse yang dikirim ke frontend.

Jalankan:
    backend/.venv/Scripts/python.exe backend/app/classifier/verify_e2e_api_response.py
"""

# ── BLOK INI HARUS PALING ATAS: set env var SEBELUM import app apapun ─────
import json
import os
import sys
from pathlib import Path

# File ini ada di: backend/app/classifier/verify_e2e_api_response.py
# parent        = backend/app/classifier/
# parent.parent = backend/app/
# parent.parent.parent = backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent

# Baca .env backend dan inject ke os.environ sebelum pydantic-settings
# membuat singleton Settings() di app.config
_env_file = BACKEND_DIR / ".env"
if _env_file.exists():
    for _raw in _env_file.read_text(encoding="utf-8").splitlines():
        _raw = _raw.strip()
        if _raw and not _raw.startswith("#") and "=" in _raw:
            _k, _v = _raw.split("=", 1)
            # Paksa overwrite (bukan setdefault) agar nilai .env selalu menang
            os.environ[_k.strip()] = _v.strip()

# Tambahkan backend ke sys.path SETELAH env var ter-set
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import cv2  # noqa: E402  (harus setelah sys.path di-set)

# Import PERSIS sama seperti routes_identify.py
from app.classifier.rule_based import classify_product
from app.db.session import SessionLocal
from app.matching.fuzzy_matcher import load_knowledge_base, match_token
from app.ocr.reader import extract_text
from app.preprocessing.pipeline import preprocess
from app.schemas.identify import BahanCocok, BahanTidakDikenali, IdentifyResponse
from app.tokenizer.tokenizer import extract_composition_section, tokenize

TARGET_PHOTO = REPO_ROOT / "dataset" / "raw_photos" / "melengkung" / "melengkung_005.jpeg"


def simulate_classify_text(raw_text: str, knowledge_base) -> IdentifyResponse:
    """Identik dengan _classify_text() di routes_identify.py."""
    tokens = tokenize(extract_composition_section(raw_text))
    hasil = classify_product([match_token(tok, knowledge_base) for tok in tokens])
    return IdentifyResponse(**hasil, raw_text=raw_text)


def main():
    # ── Konfirmasi keberadaan foto di dataset ──────────────────────────────
    if not TARGET_PHOTO.exists():
        print(f"ERROR: Foto tidak ditemukan: {TARGET_PHOTO}")
        sys.exit(1)

    print("=" * 70)
    print("KONFIRMASI FOTO")
    print("=" * 70)
    print(f"  Path  : {TARGET_PHOTO}")
    print(f"  Ukuran: {TARGET_PHOTO.stat().st_size:,} bytes")
    print("  Status: ADA dalam dataset resmi 200 foto (melengkung_001-100).")

    # ── Load knowledge base (singleton - persis seperti di production) ─────
    print("\nMemuat knowledge base dari database...")
    with SessionLocal() as session:
        knowledge_base = load_knowledge_base(session)
    print(f"  {len(knowledge_base)} entry dimuat.")

    # ── Jalankan pipeline preprocessing + OCR ─────────────────────────────
    print("\nPipeline: preprocess + OCR (EasyOCR, CPU)...")
    img = cv2.imread(str(TARGET_PHOTO))
    prep = preprocess(img)
    raw_text = extract_text(prep)           # <-- singleton reader, persis seperti API
    print(f"  OCR selesai. Panjang raw_text: {len(raw_text)} karakter.")

    # ── Jalankan classify_text PERSIS seperti endpoint ────────────────────
    response: IdentifyResponse = simulate_classify_text(raw_text, knowledge_base)

    # ── Bangun JSON output persis seperti yang dikirim ke frontend ─────────
    response_json = response.model_dump()

    print("\n" + "=" * 70)
    print("RESPONSE JSON (IdentifyResponse) - persis yang diterima frontend")
    print("=" * 70)
    # Hilangkan raw_text dari print agar tidak banjir, tapi ada di JSON penuh
    display = {k: v for k, v in response_json.items() if k != "raw_text"}
    print(json.dumps(display, indent=2, ensure_ascii=False))

    # ── Analisis deduplikasi ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ANALISIS DEDUPLIKASI RINCIAN BAHAN")
    print("=" * 70)

    # Cek apakah Susu sapi muncul duplikat
    susu_hindari = [b for b in response_json["hindari"] if "susu" in b["standard_name"].lower()]
    susu_perhatian = [b for b in response_json["perhatian"] if "susu" in b["standard_name"].lower()]
    susu_all = susu_hindari + susu_perhatian

    print(f"\nVerdict       : {response_json['verdict'].upper()}")
    print(f"Badge Hindari : {len(response_json['hindari'])} bahan (unik, sudah deduplikasi)")
    print(f"Badge Perhatian: {len(response_json['perhatian'])} bahan")
    print(f"Badge Aman    : {len(response_json['aman'])} bahan")
    print(f"Tidak Dikenali: {len(response_json['tidak_dikenali'])} token")

    print("\n--- Detail bahan HINDARI ---")
    if response_json["hindari"]:
        for b in response_json["hindari"]:
            print(f"  • {b['standard_name']}")
            print(f"    Terbaca   : \"{b['matched_window']}\"")
            print(f"    Skor      : {b['score']:.1f}")
    else:
        print("  (tidak ada)")

    print("\n--- Detail bahan PERHATIAN ---")
    if response_json["perhatian"]:
        for b in response_json["perhatian"]:
            print(f"  • {b['standard_name']}")
            print(f"    Terbaca   : \"{b['matched_window']}\"")
            print(f"    Skor      : {b['score']:.1f}")
    else:
        print("  (tidak ada)")

    print("\n--- Detail bahan AMAN ---")
    if response_json["aman"]:
        for b in response_json["aman"]:
            print(f"  • {b['standard_name']} (terbaca: \"{b['matched_window']}\", skor: {b['score']:.1f})")
    else:
        print("  (tidak ada)")

    # ── Verdict deduplikasi ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("KESIMPULAN DEDUPLIKASI")
    print("=" * 70)
    if susu_all:
        if len(susu_all) == 1:
            w = susu_all[0]["matched_window"] or ""
            bilingual_tokens = len(w.split(", ")) if w else 0
            print(f"  ✅  'Susu sapi' muncul SATU KALI di Rincian Bahan.")
            if bilingual_tokens > 1:
                print(f"  ✅  Gabungan token bilingual terbaca: \"{w}\"")
                print(f"      ({bilingual_tokens} token digabung, bukan dua baris terpisah)")
            else:
                print(f"  ℹ️   Token terbaca: \"{w}\" (satu token - tidak ada pasangan bilingual OCR-nya)")
        else:
            print(f"  ❌  'Susu sapi' MASIH muncul {len(susu_all)} kali - deduplikasi GAGAL!")
            for b in susu_all:
                print(f"      - {b['standard_name']}: \"{b['matched_window']}\"")
    else:
        print("  ℹ️   Tidak ada bahan 'Susu sapi' yang ter-match di foto ini.")
        print("       (Mungkin OCR tidak menangkap token susu/milk, atau bahan tidak ada di KB)")

    # ── Simpan JSON lengkap (dengan raw_text) ke file ─────────────────────
    out_path = REPO_ROOT / "dataset" / "debug_output" / "e2e_api_response_melengkung_005.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(response_json, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON lengkap (dengan raw_text) disimpan ke:\n  {out_path}")


if __name__ == "__main__":
    main()
