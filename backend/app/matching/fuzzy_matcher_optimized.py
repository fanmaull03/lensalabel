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
from functools import lru_cache
import json
from pathlib import Path
import re

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from sqlalchemy.orm import Session, selectinload

from app.db.models import Ingredient
from app.matching.pair_blocks import is_forbidden_pair

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

_WORD_RE = re.compile(r"[\w]+(?:-[\w]+)?", re.UNICODE)
_NEGATION_WORDS = {"bebas", "tanpa", "non"}
_NEGATION_PHRASES = {
    ("bebas",),
    ("bebas", "dari"),
    ("tanpa",),
    ("non",),
    ("tidak", "mengandung"),
}


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
    span_start: int | None = None
    span_end: int | None = None
    match_source: str = "window"
    shared_head_span: tuple[int, int] | None = None


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


def composite_score(
    a: str,
    b: str,
    weights: dict[str, float] = WEIGHTS,
    length_penalty_exponent: float = 0.8,
) -> float:
    """Weighted sum tiga algoritma, skala 0-100 dengan penalti selisih panjang karakter.
    Case-insensitive.

    Penalti berbasis selisih panjang (min_len / max_len) ** 0.8 diterapkan untuk
    mencegah kata pendek (misal "Vitamin") match ke target panjang (misal "vitamin C" /
    "Asam askorbat") tanpa merusak penanganan typo minor pada kata sedang/panjang.

    Dibulatkan 2 desimal.
    """
    a, b = a.lower(), b.lower()
    raw_score = (
        weights["levenshtein"] * fuzz.ratio(a, b)
        + weights["jaro_winkler"] * JaroWinkler.normalized_similarity(a, b) * 100
        + weights["ngram"] * ngram_similarity(a, b)
    )
    len_a, len_b = len(a), len(b)
    max_len = max(len_a, len_b)
    if max_len == 0:
        return 0.0

    length_ratio = min(len_a, len_b) / max_len
    penalty_factor = length_ratio**length_penalty_exponent
    return round(raw_score * penalty_factor, 2)


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
    word_count = len(name_variant.split())
    widths = {w for w in (word_count - 1, word_count, word_count + 1) if w >= 1}

    best_window, best_score = token, composite_score_fn(token, name_variant)
    if is_forbidden_pair(token, name_variant):
        best_score = -1.0
    for width in widths:
        for start in range(len(words) - width + 1):
            window = " ".join(words[start : start + width])
            if is_forbidden_pair(window, name_variant):
                continue
            score = composite_score_fn(window, name_variant)
            if score > best_score:
                best_window, best_score = window, score
    return best_window, max(best_score, 0.0)


def _words(value: str) -> list[str]:
    return [word.lower() for word in _WORD_RE.findall(value)]


def _has_zero_percent_negation(token: str, target_words: list[str]) -> bool:
    """Return whether an intact zero-percent unit directly precedes target."""
    if not target_words:
        return False

    target = r"\s+".join(re.escape(word) for word in target_words)
    return re.search(
        rf"(?<!\w)0(?:[.,]0+)?\s*%\s+{target}(?!\w)",
        token,
        flags=re.IGNORECASE,
    ) is not None


def _is_negated_match(token: str, matched_window: str, name_variant: str) -> bool:
    """Return whether this local candidate is explicitly negated.

    The check is anchored to the matched phrase. It never searches the whole
    token for a free-standing qualifier, so a qualifier for another ingredient
    cannot suppress this candidate.
    """
    target_words = _words(name_variant) or _words(matched_window)
    if not target_words:
        return False
    if _has_zero_percent_negation(token, target_words):
        return True

    normalized_token = re.sub(r"[^\w%-]+", " ", token.lower()).strip()
    target = r"[- ]+".join(re.escape(word) for word in target_words)
    if re.search(rf"\b{target}[- ]free\b", normalized_token):
        return True
    if re.search(rf"\bnon[- ]{target}\b", normalized_token):
        return True

    token_words = _words(token)
    if not token_words:
        return False

    target_start = None
    for index in range(len(token_words) - len(target_words) + 1):
        if token_words[index : index + len(target_words)] == target_words:
            target_start = index
            break
    if target_start is None:
        target_words = _words(name_variant)
        for index in range(len(token_words) - len(target_words) + 1):
            if token_words[index : index + len(target_words)] == target_words:
                target_start = index
                break
    if target_start is None:
        return False

    preceding = token_words[max(0, target_start - 2) : target_start]
    for phrase in _NEGATION_PHRASES:
        if len(preceding) >= len(phrase) and tuple(preceding[-len(phrase) :]) == phrase:
            return True

    target_end = target_start + len(target_words)
    following = token_words[target_end : target_end + 1]
    if following == ["free"]:
        return True

    return False


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


def load_knowledge_base_from_json(path: str | Path) -> list[dict]:
    """Load a previously exported, flattened knowledge base snapshot."""
    with Path(path).open(encoding="utf-8") as f:
        knowledge_base = json.load(f)
    if not isinstance(knowledge_base, list):
        raise ValueError("Knowledge base snapshot must contain a JSON list")
    required = {"ingredient_id", "standard_name", "category", "name_variant"}
    for index, entry in enumerate(knowledge_base):
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError(f"Invalid knowledge base entry at index {index}")
    return knowledge_base


def match_token(
    token: str,
    knowledge_base: list[dict],
    weights: dict[str, float] = WEIGHTS,
    threshold: float = THRESHOLD,
    length_penalty_exponent: float = 0.8,
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
            lambda a, b: composite_score(a, b, weights, length_penalty_exponent),
        )
        # Daftar tetap membedakan bahan seperti milk / almond milk dan
        # wheat / wheat starch. Saat skor sama, pilih jendela yang memuat
        # lebih banyak kata agar nama umum tidak menutupi bahan spesifik.
        if score > best_score or (
            score == best_score
            and len(_words(window)) > len(_words(best_window or ""))
        ):
            best_entry, best_score, best_window = entry, score, window

    if best_entry is None:  # knowledge base kosong
        return MatchResult(token=token, matched=False, score=0.0)

    # KEPUTUSAN EKSPLISIT (Tie-boundary decision):
    # Skor yang PERSIS SAMA DENGAN threshold (best_score >= threshold) dianggap MATCH.
    # Nilai threshold (misal 75.0) merepresentasikan ambang batas minimum yang diterima
    # (sesuai proposal Bab III). Hanya jika best_score < threshold (dibawah minimum)
    # token ditolak (matched=False).
    if best_score < threshold:
        # Simpan skor & variant terdekat untuk eksplorasi kalibrasi threshold.
        return MatchResult(
            token=token,
            matched=False,
            score=best_score,
            matched_window=best_window,
            matched_variant=best_entry["name_variant"],
        )

    if _is_negated_match(token, best_window, best_entry["name_variant"]):
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


_SHARED_HEAD_RE = re.compile(
    r"(?<!\w)(?P<head>Dinatrium)\s+(?P<first>Inosinat|Guanilat)"
    r"\s+dan\s+(?P<second>Inosinat|Guanilat)(?!\w)", re.IGNORECASE,
)


@lru_cache(maxsize=65536)
def _many_score(a: str, b: str, weight_items: tuple, length_penalty_exponent: float = 0.8) -> float:
    return composite_score(a, b, _weight_map(weight_items), length_penalty_exponent)


@lru_cache(maxsize=32)
def _weight_map(weight_items: tuple) -> dict:
    return dict(weight_items)


@lru_cache(maxsize=4096)
def _variant_widths(variant: str) -> tuple[int, ...]:
    word_count = len(variant.split())
    return tuple({w for w in (word_count - 1, word_count, word_count + 1) if w >= 1})


@lru_cache(maxsize=250_000)
def _cached_forbidden_pair(observed: str, variant: str) -> bool:
    return is_forbidden_pair(observed, variant)


def _score_can_reach_threshold(a: str, b: str, threshold: float, exponent: float) -> bool:
    """Safe length-only upper bound: no similarity component can exceed 100."""
    longest = max(len(a), len(b))
    if longest == 0:
        return threshold <= 0
    ratio = min(len(a), len(b)) / longest
    maximum = round(100.0 * ratio**exponent, 2)
    return maximum >= threshold


@lru_cache(maxsize=2048)
def _best_fragment(token: str, left: int, right: int, variants: tuple, weight_items: tuple,
                   length_penalty_exponent: float = 0.8, threshold: float = THRESHOLD):
    fragment = token[left:right]
    words = list(re.finditer(r"\S+", fragment))
    all_widths = sorted({width for variant in variants for width in _variant_widths(variant)})
    windows_by_width = {
        width: tuple(
            (" ".join(word[0] for word in words[offset:offset + width]),
             left + words[offset].start(), left + words[offset + width - 1].end())
            for offset in range(len(words) - width + 1)
        )
        for width in all_widths
    }
    best = None
    for index, variant in enumerate(variants):
        window = fragment
        if _score_can_reach_threshold(fragment, variant, threshold, length_penalty_exponent):
            value = _many_score(fragment.lower(), variant.lower(), weight_items, length_penalty_exponent)
        else:
            value = -1.0
        if _cached_forbidden_pair(fragment, variant):
            value = -1.0
        start, end = left, right
        for width in _variant_widths(variant):
            for candidate_window, candidate_start, candidate_end in windows_by_width[width]:
                if _cached_forbidden_pair(candidate_window, variant):
                    continue
                if not _score_can_reach_threshold(candidate_window, variant, threshold, length_penalty_exponent):
                    continue
                candidate_score = _many_score(candidate_window.lower(), variant.lower(), weight_items,
                                              length_penalty_exponent)
                if candidate_score > value:
                    window, value = candidate_window, candidate_score
                    start, end = candidate_start, candidate_end
        candidate = (value, window, start, end, index, "window", None)
        if best is None or (value, len(_words(window))) > (best[0], len(_words(best[1]))):
            best = candidate
    if best is not None and best[0] < 0:
        return None
    return best


def match_token_many(
    token: str,
    knowledge_base: list[dict],
    weights: dict[str, float] = WEIGHTS,
    threshold: float = THRESHOLD,
    *,
    shared_heads: bool = True,
    secondary_min_score: float | None = None,
    secondary_full_coverage: bool = False,
    length_penalty_exponent: float = 0.8,
) -> list[MatchResult]:
    """Greedy matches on disjoint source spans, with the original score/negation.

    Rejected negated spans are consumed too: a shorter alias must not re-enter
    through the space left by a rejected ingredient. Remaining fragments are
    scanned separately, never concatenated across a consumed span.
    """
    weight_items = tuple(sorted(weights.items()))
    variants = tuple(entry["name_variant"] for entry in knowledge_base)

    def score(a: str, b: str) -> float:
        return _many_score(a.lower(), b.lower(), weight_items, length_penalty_exponent)

    # Candidates: score, window, start, end, KB index, source, head span.
    virtual = []
    blocked = []
    if shared_heads:
        aliases = {}
        for index, entry in enumerate(knowledge_base):
            aliases.setdefault(entry["name_variant"].lower(), index)
        for phrase in _SHARED_HEAD_RE.finditer(token):
            first = f"{phrase['head']} {phrase['first']}"
            second = f"{phrase['head']} {phrase['second']}"
            if phrase['first'].lower() == phrase['second'].lower():
                continue
            if first.lower() not in aliases or second.lower() not in aliases:
                continue
            if (_is_negated_match(token, first, first)
                    or _is_negated_match(token, phrase['second'], phrase['second'])):
                # The old negation rule cannot infer the second omitted head.
                # Abstain on the whole coordinated phrase instead of inventing scope.
                blocked.append((phrase.start(), phrase.end()))
                continue
            index = aliases[second.lower()]
            virtual.append((score(second, knowledge_base[index]["name_variant"]),
                            second, phrase.start('second'), phrase.end('second'),
                            index, "shared_head", phrase.span('head')))

    def best_candidate(left: int, right: int, candidate_threshold: float = threshold):
        best = _best_fragment(token, left, right, variants, weight_items,
                              length_penalty_exponent, candidate_threshold)
        for candidate in virtual:
            if left <= candidate[2] and candidate[3] <= right:
                if best is None or (candidate[0], len(_words(candidate[1])), -candidate[4]) > (
                    best[0], len(_words(best[1])), -best[4]
                ):
                    best = candidate
        return best

    def result(candidate, accepted: bool) -> MatchResult:
        value, window, start, end, index, source, head = candidate
        entry = knowledge_base[index]
        return MatchResult(
            token=token, matched=accepted, score=value, matched_window=window,
            matched_variant=entry["name_variant"],
            ingredient_id=entry["ingredient_id"] if accepted else None,
            standard_name=entry["standard_name"] if accepted else None,
            category=entry["category"] if accepted else None,
            span_start=start, span_end=end, match_source=source, shared_head_span=head,
        )

    output = []
    fragments = [(0, len(token))]
    for start, end in blocked:
        remaining = []
        for left, right in fragments:
            if end <= left or start >= right:
                remaining.append((left, right))
            else:
                remaining.extend(((left, start), (end, right)))
        fragments = remaining
        output.append(MatchResult(token=token, matched=False, score=0.0,
                                  matched_window=token[start:end], span_start=start,
                                  span_end=end, match_source="shared_head_negation_abstained"))
    while fragments:
        choices = []
        for left, right in fragments:
            while left < right and token[left].isspace():
                left += 1
            while right > left and token[right - 1].isspace():
                right -= 1
            if left == right:
                continue
            candidate = best_candidate(left, right)
            if candidate is None or candidate[0] < threshold:
                candidate = best_candidate(left, right, 0.0)
            if candidate is None:
                output.append(MatchResult(token=token, matched=False, score=0.0,
                                          span_start=left, span_end=right))
            elif candidate[0] < threshold:
                output.append(result(candidate, False))
            else:
                choices.append((candidate, left, right))
        if not choices:
            break
        chosen, left, right = max(choices, key=lambda c: (
            c[0][0], len(_words(c[0][1])), -c[0][4], -c[0][2],
        ))
        entry = knowledge_base[chosen[4]]
        accepted = not _is_negated_match(token, chosen[1], entry["name_variant"])
        output.append(result(chosen, accepted))
        fragments = [(a, b) for candidate, a, b in choices if (a, b) != (left, right)]
        fragments.extend(((left, chosen[2]), (chosen[3], right)))
    # Preserve the classifier's token-level unknown policy: an already matched
    # token did not turn unknown because it also contained qualifiers or noise.
    accepted = [match for match in output if match.matched]
    from app.matching.secondary_guards import filter_secondary_matches
    return filter_secondary_matches(
        accepted or output or [MatchResult(token=token, matched=False, score=0.0)],
        minimum_score=secondary_min_score, full_coverage=secondary_full_coverage,
    )
