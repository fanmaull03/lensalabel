"""Read-only spelling, code, short-alias, and superset audit for KB v2."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from openpyxl import load_workbook
from rapidfuzz.distance import Levenshtein


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.matching.fuzzy_matcher import composite_score  # noqa: E402


OUT = ROOT / "evaluation/results/kb_v2_phase2"
V1 = ROOT / "evaluation/kb_snapshot.json"
OLD_AUDIT = ROOT / "dataset/ground_truth/calibration_kb_risk_audit_v3.xlsx"
WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokens(value: str) -> tuple[str, ...]:
    return tuple(WORD.findall(value.casefold()))


def write_csv(name: str, rows: list[dict], columns: list[str]) -> None:
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def variant_rows(items: list[dict]) -> list[dict]:
    return [{"id": item["new_entry_id"], "name": item["standard_name"],
             "category": item["category"], "variant": variant, "words": tokens(variant),
             "is_new_entry": not bool(item["old_numbers"])}
            for item in items for variant in [item["standard_name"], *item["synonyms"]]]


def ordered_subset(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    iterator = iter(long)
    return all(any(word == target for word in iterator) for target in short)


def superset_pairs(rows: list[dict], *, new_only: bool, old_variants: set[tuple[str, ...]]) -> dict:
    by_word = defaultdict(list)
    for row in rows:
        if len(row["words"]) <= 9:
            for word in set(row["words"]):
                by_word[word].append(row)
    witnesses = {}
    for short in rows:
        if not 1 <= len(short["words"]) <= 3 or not short["words"]:
            continue
        pivot = min(short["words"], key=lambda word: len(by_word[word]))
        for long in by_word[pivot]:
            if short["id"] == long["id"] or len(long["words"]) <= len(short["words"]):
                continue
            if new_only and not (short["is_new_entry"] or long["is_new_entry"]
                                 or short["words"] not in old_variants or long["words"] not in old_variants):
                continue
            if not ordered_subset(short["words"], long["words"]):
                continue
            key = (short["id"], long["id"])
            witness = {"bahan_umum": short["name"], "bahan_spesifik": long["name"],
                       "id_umum": short["id"], "id_spesifik": long["id"],
                       "kategori_umum": short["category"], "kategori_spesifik": long["category"],
                       "varian_umum": short["variant"], "varian_spesifik": long["variant"],
                       "kata_tambahan": " ".join(word for word in long["words"] if word not in short["words"]),
                       "status": "LAPORKAN_TANPA_ATURAN_OTOMATIS"}
            if key not in witnesses or (len(long["words"]) - len(short["words"]), len(long["variant"])) < (
                    len(tokens(witnesses[key]["varian_spesifik"])) - len(tokens(witnesses[key]["varian_umum"])),
                    len(witnesses[key]["varian_spesifik"])):
                witnesses[key] = witness
    return witnesses


def main() -> None:
    payload = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    items = payload["ingredients"]
    rows = variant_rows(items)
    old = json.loads(V1.read_text(encoding="utf-8"))
    old_variants = {tokens(row["name_variant"]) for row in old}
    word_map = defaultdict(lambda: defaultdict(set))
    for row in rows:
        for word in set(row["words"]):
            word_map[word][row["id"]].add(row["variant"])
    words = sorted(word_map)
    old_words = {word for row in old for word in tokens(row["name_variant"])}
    old_wb = load_workbook(OLD_AUDIT, read_only=True, data_only=True)
    old_word_pairs = {frozenset((a, b)) for a, b, *_ in list(old_wb["pasangan_kata"].values)[1:]}
    old_wb.close()
    word_pairs = []
    for a, b in combinations(words, 2):
        if min(len(a), len(b)) < 5 or Levenshtein.distance(a, b, score_cutoff=1) != 1:
            continue
        ids_a, ids_b = set(word_map[a]), set(word_map[b])
        if not any(i != j for i in ids_a for j in ids_b):
            continue
        word_pairs.append({"kata_a": a, "kata_b": b, "edit_distance": 1,
                           "bahan_a": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i) for i in ids_a})),
                           "bahan_b": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i) for i in ids_b})),
                           "score_komposit": composite_score(a, b),
                           "status_vs_v3": "WARISAN_V3" if frozenset((a, b)) in old_word_pairs else "BARU_DARI_V2_ATAU_CAKUPAN_AUDIT",
                           "status": "REVIEW_MANUAL_JANGAN_AKTIFKAN"})
    write_csv("risk_word_pairs.csv", word_pairs, list(word_pairs[0]))

    short_new_pairs = []
    seen_short_pairs = set()
    for a in words:
        if a in old_words or len(a) < 3:
            continue
        for b in words:
            if a == b or len(b) < 3 or abs(len(a) - len(b)) > 1:
                continue
            if Levenshtein.distance(a, b, score_cutoff=1) != 1:
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen_short_pairs:
                continue
            if not any(i != j for i in word_map[a] for j in word_map[b]):
                continue
            seen_short_pairs.add(pair)
            short_new_pairs.append({"kata_a": pair[0], "kata_b": pair[1],
                                    "score_komposit": composite_score(*pair),
                                    "bahan_a": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i)
                                                                   for i in word_map[pair[0]]})),
                                    "bahan_b": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i)
                                                                   for i in word_map[pair[1]]})),
                                    "status": "USUL_AUDIT_BELUM_BLOKIR"})
    short_new_pairs.sort(key=lambda row: row["score_komposit"], reverse=True)
    write_csv("risk_new_minimal_pairs.csv", short_new_pairs,
              ["kata_a", "kata_b", "score_komposit", "bahan_a", "bahan_b", "status"])

    short_rows = []
    for short in payload["short_new_variants_for_review"]:
        owner = short["new_entry_id"]
        category = next(item["category"] for item in items if item["new_entry_id"] == owner)
        candidates = [(composite_score(short["variant"], other["variant"]), other)
                      for other in rows if other["id"] != owner and other["category"] != category]
        score, best = max(candidates, key=lambda pair: (pair[0], -len(pair[1]["variant"])))
        short_rows.append({**short, "category": category, "max_score_different_category": score,
                           "nearest_variant": best["variant"], "nearest_standard_name": best["name"],
                           "nearest_category": best["category"], "nearest_new_entry_id": best["id"]})
    write_csv("risk_short_variants_52.csv", short_rows, list(short_rows[0]))

    code_rows = []
    codes = defaultdict(set)
    for row in rows:
        v = row["variant"].replace(" ", "").casefold()
        if re.fullmatch(r"(?:ins|e)\d+[a-z]?(?:\([ivx]+\))?", v):
            codes[v].add(row["id"])
    for a, b in combinations(sorted(codes), 2):
        ia, ib = set(codes[a]), set(codes[b])
        if not any(i != j for i in ia for j in ib):
            continue
        ca, cb = re.sub(r"^(ins|e)", "", a), re.sub(r"^(ins|e)", "", b)
        if ca != cb and Levenshtein.distance(ca, cb, score_cutoff=1) > 1:
            continue
        code_rows.append({"kode_a": a, "kode_b": b, "id_a": " | ".join(sorted(ia)),
                          "id_b": " | ".join(sorted(ib)), "jenis": "kode_sama" if ca == cb else "beda_satu_karakter",
                          "status": "MATCH_KODE_TETAP_EXACT; LAPORKAN_DUPLIKAT_LINTAS_ENTRI"})
    write_csv("risk_ins_codes.csv", code_rows,
              ["kode_a", "kode_b", "id_a", "id_b", "jenis", "status"])

    super_rows = list(superset_pairs(rows, new_only=True, old_variants=old_variants).values())
    super_rows.sort(key=lambda row: (row["bahan_umum"], row["bahan_spesifik"]))
    write_csv("risk_new_supersets.csv", super_rows,
              ["bahan_umum", "bahan_spesifik", "id_umum", "id_spesifik", "kategori_umum", "kategori_spesifik",
               "varian_umum", "varian_spesifik", "kata_tambahan", "status"])

    families = [
        ["malt", "maltodekstrin", "maltitol", "maltosa", "maltol"],
        ["gluten", "glutamat"],
        ["laktosa", "laktat", "laktalbumin"],
    ]
    family_rows = []
    for family in families:
        for a, b in combinations(family, 2):
            family_rows.append({"keluarga": " / ".join(family), "kata_a": a, "kata_b": b,
                                "ada_a_di_kb_v2": a in word_map, "ada_b_di_kb_v2": b in word_map,
                                "edit_distance": Levenshtein.distance(a, b),
                                "score_komposit": composite_score(a, b),
                                "bahan_a": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i)
                                                               for i in word_map.get(a, {})})),
                                "bahan_b": " | ".join(sorted({next(x["name"] for x in rows if x["id"] == i)
                                                               for i in word_map.get(b, {})})),
                                "status": "AUDIT_SAJA_BELUM_BLOKIR"})
    write_csv("risk_target_families.csv", family_rows, list(family_rows[0]))
    summary = {"word_pairs_total": len(word_pairs),
               "word_pairs_not_in_v3": sum(x["status_vs_v3"] != "WARISAN_V3" for x in word_pairs),
               "word_pairs_with_new_word": sum(x["kata_a"] not in old_words or x["kata_b"] not in old_words
                                               for x in word_pairs),
               "new_minimal_pairs": len(short_new_pairs),
               "short_variants_checked": len(short_rows),
               "short_variant_max_score_ge_75": sum(x["max_score_different_category"] >= 75 for x in short_rows),
               "short_variant_max_score_ge_80": sum(x["max_score_different_category"] >= 80 for x in short_rows),
               "code_pairs": len(code_rows), "new_superset_relations": len(super_rows),
               "target_family_pairs": len(family_rows)}
    (OUT / "risk_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
