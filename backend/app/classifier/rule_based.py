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

    Deduplikasi Rincian Bahan:
    Jika beberapa token dalam satu komposisi match ke entry kanonis yang sama
    (misalnya token bilingual 'Susu Segar' dan 'Fresh Milk' -> 'Susu sapi'),
    maka mereka dikelompokkan menjadi satu baris per bahan kanonis. Field
    matched_window menggabungkan semua potongan teks yang terbaca.
    """
    result = {cat: [] for cat in CATEGORIES}
    result[UNKNOWN_GROUP] = []

    # Kelompokkan bahan yang cocok berdasarkan kategori dan nama kanonis (standard_name)
    grouped_matched: dict[str, dict[str, dict]] = {cat: {} for cat in CATEGORIES}

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

        cat = m.category
        if cat not in grouped_matched:
            continue

        std_name = m.standard_name
        window_text = (m.matched_window if m.matched_window is not None else m.token).strip()

        if std_name not in grouped_matched[cat]:
            grouped_matched[cat][std_name] = {
                "standard_name": std_name,
                "matched_windows": [window_text] if window_text else [],
                "scores": [m.score],
            }
        else:
            entry = grouped_matched[cat][std_name]
            if window_text and window_text not in entry["matched_windows"]:
                entry["matched_windows"].append(window_text)
            entry["scores"].append(m.score)

    # Susun rincian bahan kanonis per kategori
    for cat in CATEGORIES:
        for std_name, entry in grouped_matched[cat].items():
            result[cat].append(
                {
                    "standard_name": entry["standard_name"],
                    "matched_window": ", ".join(entry["matched_windows"]) if entry["matched_windows"] else None,
                    "score": max(entry["scores"]) if entry["scores"] else 0.0,
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

