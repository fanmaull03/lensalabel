"""Tahap 6 - Rule-based classifier: Aman / Perhatian / Hindari.

Klasifikasi per bahan sudah ditentukan knowledge base (kolom category), jadi
tahap ini tidak menilai ulang tiap bahan; tugasnya mengelompokkan hasil
matching Tahap 5 lalu menyimpulkan satu verdict untuk keseluruhan produk.
"""

from __future__ import annotations

from app.matching.fuzzy_matcher import MatchResult

CATEGORIES = ("aman", "perhatian", "hindari")
UNKNOWN_GROUP = "tidak_dikenali"


def classify_product(matches: list[MatchResult]) -> dict:
    """Kelompokkan hasil matching per kategori + tentukan verdict produk.

    Aturan IF-THEN verdict, dievaluasi berurutan (keputusan desain BAB III).
    Aturan 0 dicek paling awal; kalau matches tidak kosong, aturan 1-4 jalan
    seperti biasa:
      0. matches kosong (tidak ada token sama sekali) -> "tidak_terbaca"
      1. ada >= 1 bahan kategori 'hindari'            -> "hindari"
      2. tidak ada 'hindari', ada >= 1 'perhatian'    -> "perhatian"
      3. semua matched 'aman' DAN tidak ada unmatched -> "aman"
      4. semua matched 'aman' TAPI ada unmatched      -> "perlu_verifikasi"

    Aturan 0 sengaja memakai status sendiri, bukan "perlu_verifikasi": keduanya
    beda makna. "perlu_verifikasi" = komposisi terbaca sebagian tapi ada yang
    tidak dikenali; "tidak_terbaca" = tidak ada komposisi yang berhasil dibaca
    sama sekali (OCR atau tokenisasi gagal), jadi yang perlu diulang fotonya,
    bukan bahannya yang perlu diperiksa.

    Aturan 4 sengaja tidak menyimpulkan "aman": token yang gagal di-match bisa
    saja bahan berisiko yang tidak dikenali sistem, sehingga menyebut produk
    aman berarti menyembunyikan ketidaktahuan dari orang tua. Karena itu token
    unmatched juga tetap dilaporkan di grup 'tidak_dikenali', bukan dibuang.
    """
    result = {cat: [] for cat in CATEGORIES}
    result[UNKNOWN_GROUP] = []

    for m in matches:
        if not m.matched:
            result[UNKNOWN_GROUP].append(
                {
                    "token": m.token,
                    "score": m.score,
                    "terdekat": m.matched_variant,
                }
            )
            continue
        result[m.category].append(
            {
                "standard_name": m.standard_name,
                "matched_window": m.matched_window,
                "score": m.score,
            }
        )

    if not matches:
        verdict = "tidak_terbaca"
    elif result["hindari"]:
        verdict = "hindari"
    elif result["perhatian"]:
        verdict = "perhatian"
    elif result[UNKNOWN_GROUP]:
        verdict = "perlu_verifikasi"
    else:
        verdict = "aman"

    result["verdict"] = verdict
    return result
