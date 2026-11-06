"""Pencocokan anotasi kalibrasi: exact dahulu, lenient hanya untuk review."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import distance
from app.matching.pair_blocks import is_forbidden_pair, pair_data

from app.matching.fuzzy_matcher import _is_negated_match

TERM_MAP = {
    "glutamate": "glutamat", "glutamat": "glutamat",
    "mononatriurn": "mononatrium", "flavour": "perisa", "flavor": "perisa",
    "synthetic": "sintetik", "acid": "asam", "sodium": "natrium",
    "sugar": "gula", "ascorbic": "askorbat", "benzoate": "benzoat",
    "colour": "pewarna", "color": "pewarna", "acesulfame": "asesulfam",
    "sucralose": "sukralosa", "cyclamate": "siklamat", "saccharin": "sakarin",
}

# Pengecualian identitas bahan terhadap toleransi typo, bukan penghapusan
# toleransi typo. Seluruh pasangan berikut sudah dikonfirmasi pengguna.
FORBIDDEN_TYPO_PAIRS = frozenset(frozenset(pair) for pair in pair_data()["active_pairs"])
SHORT_WORD_TYPO_PAIRS = frozenset({frozenset({"susu", "susuu"})})
_PHRASE_BOUNDARY = re.compile(r"[,;()\[\]{}]")
TAXONOMY_SOURCE = "ambigu_taksonomi_tunggu_ahli_gizi"
# Inventaris relasi hasil audit, hanya untuk penandaan review. Bukan aturan
# penghapusan/penggabungan bahan dan tidak mengubah knowledge base.
TAXONOMY_REVIEW_PAIRS = frozenset(
    (row["short_name"], row["long_name"])
    for row in json.loads(Path(__file__).with_name("lenient_taxonomy_review_pairs.json").read_text(encoding="utf-8"))
)


@dataclass(frozen=True)
class Occurrence:
    ingredient_id: int
    standard_name: str
    category: str
    matched_variant: str
    start: int
    end: int
    negated: bool
    edits: int = 0
    gaps: int = 0


def normalize_words(text: str) -> list[str]:
    return [TERM_MAP.get(match[0].lower(), match[0].lower())
            for match in re.finditer(r"\w+", text)]


def is_word_fuzzy_match(w1: str, w2: str) -> bool:
    if w1 == w2:
        return True
    # Kode INS/E maupun token angka harus cocok persis. Satu angka berbeda
    # dapat menunjuk aditif berbeda, sehingga bukan typo yang ditoleransi.
    if any(character.isdigit() for character in w1 + w2):
        return False
    pair = frozenset({w1, w2})
    if pair in FORBIDDEN_TYPO_PAIRS or is_forbidden_pair(w1, w2):
        return False
    return w1 == w2 or pair in SHORT_WORD_TYPO_PAIRS or (
        len(w1) >= 6 and len(w2) >= 6
        and distance.Levenshtein.distance(w1, w2) <= 1
    )


def _has_phrase_boundary(text: str, left: int, right: int) -> bool:
    for match in _PHRASE_BOUNDARY.finditer(text, left, right):
        index = match.start()
        # Koma desimal pada 0,5 bukan pemisah dua bahan.
        if text[index] == "," and index > 0 and index + 1 < len(text):
            if text[index - 1].isdigit() and text[index + 1].isdigit():
                continue
        return True
    return False


def _ordered_subset(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    iterator = iter(long)
    return all(any(word == target for word in iterator) for target in short)


def _specificity_is_authorized(short: Occurrence, long: Occurrence) -> bool:
    # Cakupan awal yang sudah diminta eksplisit: kelapa vs kelapa sawit.
    return short.standard_name == "Minyak kelapa" and "sawit" in normalize_words(long.standard_name)


def _prefer_specific(matches: list[Occurrence], positions: dict[Occurrence, tuple[int, ...]],
                     taxonomy_details: dict | None = None) -> list[Occurrence]:
    words = {match: tuple(normalize_words(match.matched_variant)) for match in matches}
    result = []
    for match in matches:
        specific_matches = [other for other in matches if (
            other.ingredient_id != match.ingredient_id and not other.negated
            and len(words[other]) > len(words[match])
            and _ordered_subset(words[match], words[other])
            and set(positions[match]).issubset(positions[other])
        )]
        suppressed = any(_specificity_is_authorized(match, other) for other in specific_matches)
        if taxonomy_details is not None and not match.negated:
            for other in specific_matches:
                if _specificity_is_authorized(match, other):
                    continue
                if (match.standard_name, other.standard_name) not in TAXONOMY_REVIEW_PAIRS:
                    continue
                detail = {"bahan_umum": match.standard_name, "bahan_spesifik": other.standard_name,
                          "varian_umum": match.matched_variant, "varian_spesifik": other.matched_variant,
                          "start": other.start, "end": other.end}
                for occurrence in (match, other):
                    taxonomy_details.setdefault(occurrence, []).append(detail)
        if not suppressed:
            result.append(match)
    return result


def _negated(text: str, start: int, end: int) -> bool:
    # Periksa kemunculan ini, bukan kemunculan pertama nama di seluruh label.
    prefix = list(re.finditer(r"\S+", text[:start]))
    left = prefix[-2].start() if len(prefix) >= 2 else 0
    boundaries = list(re.finditer(r"[;:\n]|,(?!\d)", text[left:start]))
    if boundaries:
        left += boundaries[-1].end()
    suffix = re.search(r"\S+", text[end:])
    right = end + suffix.end() if suffix else end
    matched = text[start:end]
    earlier = list(re.finditer(re.escape(matched), text[left:start], flags=re.IGNORECASE))
    if earlier:
        left += earlier[-1].end()
    return _is_negated_match(text[left:right], matched, matched)


def exact_occurrences(text: str, kb: list[dict]) -> list[Occurrence]:
    matches = []
    for entry in kb:
        variant = entry["name_variant"].strip()
        if not variant:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in variant.split()) + r"(?!\w)"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            matches.append(Occurrence(
                entry["ingredient_id"], entry["standard_name"], entry["category"],
                entry["name_variant"], match.start(), match.end(),
                _negated(text, match.start(), match.end()),
            ))
    return matches


def strict_ingredients(text: str, kb: list[dict]) -> list[dict]:
    matches = [match for match in exact_occurrences(text, kb) if not match.negated]
    # Minyak kelapa di dalam Minyak kelapa sawit, atau Milk di dalam Almond
    # milk, adalah penyebutan bahan spesifik yang sama, bukan dua bahan.
    specific = [match for match in matches if not any(
        other.ingredient_id != match.ingredient_id
        and other.start <= match.start and match.end <= other.end
        and other.end - other.start > match.end - match.start
        for other in matches
    )]
    grouped = defaultdict(list)
    for match in specific:
        grouped[match.ingredient_id].append(match)
    ingredients = []
    for iid, occurrences in sorted(grouped.items()):
        match = min(occurrences, key=lambda m: (-(m.end - m.start), m.start, m.matched_variant))
        ingredients.append({
            "ingredient_id": iid, "standard_name": match.standard_name,
            "category": match.category, "matched_variant": match.matched_variant,
        })
    return ingredients


def lenient_occurrences(text: str, kb: list[dict], *, taxonomy_details: dict | None = None) -> list[Occurrence]:
    spans = list(re.finditer(r"\w+", text))
    words = normalize_words(text)
    matches = []
    seen = set()
    matched_positions = {}
    for entry in kb:
        variant_words = normalize_words(entry["name_variant"])
        if not variant_words:
            continue
        code_variant = (len(variant_words) == 2 and variant_words[0] in {"ins", "e"}
                        and re.fullmatch(r"\d+[a-z]?", variant_words[1]) is not None)
        # INS 250 merupakan satu kode. Jangan merakit INS dari satu kode
        # dengan angka kode lain melalui toleransi kata sisipan.
        extra_words = 0 if code_variant else 3
        for start in range(len(words)):
            if not is_word_fuzzy_match(words[start], variant_words[0]):
                continue
            positions = [start]
            pointer = 1
            edits = distance.Levenshtein.distance(words[start], variant_words[0])
            # Aturan lama: urutan kata tetap, maksimal tiga kata sisipan.
            for index in range(start + 1, min(len(words), start + len(variant_words) + extra_words)):
                if pointer == len(variant_words):
                    break
                if _has_phrase_boundary(text, spans[index - 1].end(), spans[index].start()):
                    break
                if is_word_fuzzy_match(words[index], variant_words[pointer]):
                    edits += distance.Levenshtein.distance(words[index], variant_words[pointer])
                    positions.append(index)
                    pointer += 1
            if pointer != len(variant_words):
                continue
            left, right = spans[start].start(), spans[positions[-1]].end()
            key = (entry["ingredient_id"], entry["name_variant"], left, right)
            if key in seen:
                continue
            seen.add(key)
            occurrence = Occurrence(
                entry["ingredient_id"], entry["standard_name"], entry["category"],
                entry["name_variant"], left, right, _negated(text, left, right),
                edits, positions[-1] - start + 1 - len(variant_words),
            )
            matches.append(occurrence)
            matched_positions[occurrence] = tuple(positions)
    return _prefer_specific(matches, matched_positions, taxonomy_details)


def review_rows(filename: str, text: str, ingredients: list[dict], kb: list[dict]) -> list[dict]:
    strict_ids = {ingredient["ingredient_id"] for ingredient in ingredients}
    grouped = defaultdict(list)
    taxonomy_details = {}
    for match in lenient_occurrences(text, kb, taxonomy_details=taxonomy_details):
        grouped[match.ingredient_id].append(match)
    rows = []
    text_words = list(re.finditer(r"\S+", text))
    for iid, matches in sorted(grouped.items()):
        if iid in strict_ids:
            continue
        positive = [match for match in matches if not match.negated]
        ambiguities = {
            json.dumps(detail, ensure_ascii=False, sort_keys=True): detail
            for occurrence in positive for detail in taxonomy_details.get(occurrence, [])
        }
        match = min(positive or matches, key=lambda m: (m.edits, m.gaps, -(m.end - m.start), m.start))
        first = next((i for i, word in enumerate(text_words) if word.end() > match.start), 0)
        last = next((i for i, word in enumerate(text_words) if word.end() >= match.end), len(text_words) - 1)
        left = text_words[max(0, first - 8)].start()
        right = text_words[min(len(text_words) - 1, last + 8)].end()
        rows.append({
            "filename": filename, "standard_name": match.standard_name,
            "category": match.category,
            "sumber": TAXONOMY_SOURCE if ambiguities else "lenient_only" if positive else "dibuang_negasi",
            "potongan_teks": f"... {text[left:right]} ...", "keputusan": "",
            "ingredient_id": iid, "matched_variant": match.matched_variant,
            "matched_text": text[match.start:match.end],
            "relasi_taksonomi": [dict(detail, matched_text=text[detail["start"]:detail["end"]])
                                 for detail in ambiguities.values()],
        })
    return rows


def joined_spelling_review_rows(filename: str, text: str, ingredients: list[dict], kb: list[dict]) -> list[dict]:
    """Review-only exact letter concatenation across whitespace/hyphens.

    No typo expansion, punctuation crossing, digit codes, or automatic GT merge.
    At most four words and at least six letters avoid short accidental joins.
    """
    existing = {x['ingredient_id'] for x in ingredients}
    ordinary = {x['ingredient_id'] for x in review_rows(filename, text, ingredients, kb)}
    spans = list(re.finditer(r'\w+', text))
    found = {}
    for entry in kb:
        iid = entry['ingredient_id']
        if iid in existing or iid in ordinary or iid in found:
            continue
        variant_words = re.findall(r'\w+', entry['name_variant'].lower())
        letters = ''.join(variant_words)
        if not letters.isalpha() or len(letters) < 6 or len(variant_words) > 4:
            continue
        for index in range(len(spans)):
            for width in range(1, 5):
                selected = spans[index:index + width]
                if len(selected) != width:
                    continue
                observed = [s[0].lower() for s in selected]
                left, right = selected[0].start(), selected[-1].end()
                separators = [text[a.end():b.start()] for a,b in zip(selected,selected[1:])]
                if any(not re.fullmatch(r'[\s-]+', separator) for separator in separators):
                    continue
                if observed == variant_words or ''.join(observed) != letters or _negated(text, left, right):
                    continue
                found[iid] = dict(filename=filename, standard_name=entry['standard_name'],
                    category=entry['category'], ingredient_id=iid, sumber='ejaan_menyatu_terpisah_review',
                    matched_variant=entry['name_variant'], matched_text=text[left:right],
                    potongan_teks=text[max(0,left-75):min(len(text),right+75)], keputusan='')
                break
            if iid in found:
                break
    return list(found.values())
