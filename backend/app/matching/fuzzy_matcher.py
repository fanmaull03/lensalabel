"""Tahap 5 - Rule-Based Fuzzy String Matching (composite similarity score).

Tiga algoritma digabung jadi satu skor komposit lewat weighted sum, sesuai
proposal BAB II.7 & BAB III.3.4.4:
  1. Levenshtein ratio  - rapidfuzz.fuzz.ratio()
  2. Jaro-Winkler       - rapidfuzz.distance.JaroWinkler
  3. N-Gram similarity  - koefisien Dice pada character bigram (implementasi
                          sendiri, RapidFuzz tidak menyediakan)

Semua skor diskalakan 0-100 supaya bisa dijumlahkan berbobot.
Semua perbandingan case-insensitive, karena tokenizer Tahap 4 sengaja tidak
melakukan lowercase.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from sqlalchemy.orm import Session, selectinload

from app.db.models import Ingredient

# --- Knob kalibrasi ---------------------------------------------------------
# PLACEHOLDER AWAL, BELUM DIKALIBRASI SECARA EMPIRIS. Bobot sengaja dimulai
# sama rata karena belum ada bukti algoritma mana yang paling berkontribusi.
# Kalibrasi formal (bobot + threshold) dilakukan di Tahap 9 memakai
# Precision/Recall/F1 terhadap ground truth, bukan ditebak di sini.
WEIGHTS = {
    "levenshtein": 1 / 3,
    "jaro_winkler": 1 / 3,
    "ngram": 1 / 3,
}
THRESHOLD = 75.0  # skor komposit minimal supaya token dianggap cocok
NGRAM_SIZE = 2    # bigram karakter


@dataclass
class MatchResult:
    """Hasil pencocokan satu token ke knowledge base.

    Saat unmatched, field bahan (ingredient_id/standard_name/category) None,
    tapi score dan matched_variant tetap diisi supaya bisa dipakai
    mengeksplorasi kalibrasi threshold nanti.

    matched_window = potongan teks di dalam token yang benar-benar dinilai,
    dipisah dari token utuh supaya review manual bisa membedakan match asli
    dari match kebetulan.
    """

    token: str
    matched: bool
    score: float
    matched_window: str | None = None
    matched_variant: str | None = None
    ingredient_id: int | None = None
    standard_name: str | None = None
    category: str | None = None


def _bigrams(text: str) -> Counter:
    """Character n-gram sebagai multiset (bigram berulang tetap dihitung)."""
    return Counter(text[i : i + NGRAM_SIZE] for i in range(len(text) - NGRAM_SIZE + 1))


def ngram_similarity(a: str, b: str) -> float:
    """Koefisien Dice pada character bigram, skala 0-100.

    Dice = 2 * |irisan| / (|A| + |B|).
    """
    grams_a, grams_b = _bigrams(a), _bigrams(b)
    total = sum(grams_a.values()) + sum(grams_b.values())
    if total == 0:  # kedua string lebih pendek dari NGRAM_SIZE
        return 100.0 if a == b else 0.0
    overlap = sum((grams_a & grams_b).values())
    return 200.0 * overlap / total


def composite_score(a: str, b: str, weights: dict[str, float] = WEIGHTS) -> float:
    """Weighted sum tiga algoritma, skala 0-100. Case-insensitive.

    Dibulatkan 2 desimal: bobot 1/3 bikin string identik jadi 99.99999999999999,
    yang menyesatkan saat dibaca di laporan evaluasi.
    """
    a, b = a.lower(), b.lower()
    score = (
        weights["levenshtein"] * fuzz.ratio(a, b)
        + weights["jaro_winkler"] * JaroWinkler.normalized_similarity(a, b) * 100
        + weights["ngram"] * ngram_similarity(a, b)
    )
    return round(score, 2)


def find_best_window(
    token: str,
    name_variant: str,
    composite_score_fn=composite_score,
) -> tuple[str, float]:
    """Cari potongan kata dalam token yang paling mirip name_variant.

    OCR sering kehilangan koma, sehingga satu token bisa berisi 3-4 nama bahan
    sekaligus. Membandingkan token utuh lawan name_variant yang cuma 1-4 kata
    tidak adil: string panjang lawan string pendek selalu skornya rendah walau
    nama bahannya ada di dalam situ. Jadi yang dibandingkan bukan token utuh,
    tapi jendela kata sepanjang name_variant yang digeser di sepanjang token.

    Algoritmanya tidak berubah, tetap composite_score() yang sama; yang berubah
    hanya UNIT teks yang masuk ke sana.

    Lebar jendela dicoba word_count-1, word_count, dan word_count+1 sebagai
    toleransi kalau OCR menambah atau menghilangkan satu kata.
    """
    words = token.split()
    if len(words) <= 2:  # token lebih pendek dari name_variant, tidak ada yang digeser
        return token, composite_score_fn(token, name_variant)

    word_count = len(name_variant.split())
    widths = {w for w in (word_count - 1, word_count, word_count + 1) if w >= 1}

    best_window, best_score = token, composite_score_fn(token, name_variant)
    for width in widths:
        for start in range(len(words) - width + 1):
            window = " ".join(words[start : start + width])
            score = composite_score_fn(window, name_variant)
            if score > best_score:
                best_window, best_score = window, score
    return best_window, best_score


def load_knowledge_base(session: Session) -> list[dict]:
    """Ambil semua bahan + sinonimnya, flatten jadi satu entri per name_variant."""
    ingredients = (
        session.query(Ingredient).options(selectinload(Ingredient.synonyms)).all()
    )

    knowledge_base = []
    for ing in ingredients:
        variants = [ing.standard_name] + [s.synonym for s in ing.synonyms]
        for variant in variants:
            knowledge_base.append(
                {
                    "ingredient_id": ing.id,
                    "standard_name": ing.standard_name,
                    "category": ing.category.value,
                    "name_variant": variant,
                }
            )
    return knowledge_base


def match_token(
    token: str,
    knowledge_base: list[dict],
    weights: dict[str, float] = WEIGHTS,
    threshold: float = THRESHOLD,
) -> MatchResult:
    """Cocokkan token ke semua name_variant, ambil skor tertinggi (top-1).

    Yang dibandingkan adalah jendela kata terbaik di dalam token (lihat
    find_best_window), bukan token utuh.
    """
    # Mulai dari -1, bukan 0: token yang skornya 0 ke semua entri tetap harus
    # punya best_entry, supaya matched_variant-nya tidak hilang.
    best_entry, best_score, best_window = None, -1.0, None
    for entry in knowledge_base:
        window, score = find_best_window(
            token,
            entry["name_variant"],
            lambda a, b: composite_score(a, b, weights),
        )
        if score > best_score:
            best_entry, best_score, best_window = entry, score, window

    if best_entry is None:  # knowledge base kosong
        return MatchResult(token=token, matched=False, score=0.0)

    if best_score < threshold:
        # Simpan skor & variant terdekat untuk eksplorasi kalibrasi threshold.
        return MatchResult(
            token=token,
            matched=False,
            score=best_score,
            matched_window=best_window,
            matched_variant=best_entry["name_variant"],
        )

    return MatchResult(
        token=token,
        matched=True,
        score=best_score,
        matched_window=best_window,
        matched_variant=best_entry["name_variant"],
        ingredient_id=best_entry["ingredient_id"],
        standard_name=best_entry["standard_name"],
        category=best_entry["category"],
    )
