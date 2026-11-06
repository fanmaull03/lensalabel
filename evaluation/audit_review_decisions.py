"""Audit accepted Y decisions in an ingredient-review workbook (read-only)."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]


def _is_negated_match(context: str, actual: str, variant: str) -> bool:
    """Small read-only negation check for review audit, independent of runtime."""
    escaped = re.escape(actual.strip())
    if not escaped:
        return False
    return bool(re.search(r"\b(?:bebas|tanpa|free\s+from|without)\b[^,.;]{0,36}" + escaped,
                          context, re.IGNORECASE))


def words_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\w+", text, re.UNICODE)]


def typo_word_match(a: str, b: str) -> tuple[bool, bool]:
    a, b = a.casefold(), b.casefold()
    if a == b:
        return True, False
    if len(a) < 6 or len(b) < 6 or abs(len(a) - len(b)) > 1:
        return False, True
    # A bounded edit-distance-one check avoids a runtime dependency.
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1; j += 1
            continue
        edits += 1
        if edits > 1:
            return False, True
        if len(a) > len(b): i += 1
        elif len(b) > len(a): j += 1
        else: i += 1; j += 1
    edits += int(i < len(a) or j < len(b))
    return edits <= 1, True


def exact_spans(text: str, phrase: str) -> list[tuple[int, int]]:
    parts = [re.escape(x) for x in phrase.split() if x]
    if not parts:
        return []
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def unordered_phrase_spans(text: str, phrase: str, max_words: int = 8) -> list[tuple[int, int]]:
    """Locate all exact phrase words in a short local span, regardless of order."""
    targets = [w.casefold() for w in phrase.split() if w]
    source = words_with_spans(text)
    if not targets:
        return []
    candidates = []
    for left in range(len(source)):
        for right in range(left, min(len(source), left + max_words)):
            local = [source[i][0].casefold() for i in range(left, right + 1)]
            if all(word in local for word in targets):
                candidates.append((source[left][1], source[right][2]))
                break
    if not candidates:
        return []
    width = min(end - start for start, end in candidates)
    return [span for span in candidates if span[1] - span[0] == width]


def aligned_spans(text: str, phrase: str, max_gaps: int = 3) -> list[tuple[int, int, bool]]:
    """Find ordered whole-word alignments with up to three intervening words."""
    target = phrase.split()
    source = words_with_spans(text)
    if not target or not source:
        return []
    found: list[tuple[int, int, bool]] = []

    def walk(target_index: int, source_index: int, chosen: list[int], used_similarity: bool) -> None:
        if target_index == len(target):
            found.append((source[chosen[0]][1], source[chosen[-1]][2], used_similarity))
            return
        stop = len(source) if not chosen else min(len(source), chosen[-1] + max_gaps + 2)
        for idx in range(source_index, stop):
            ok, fuzzy = typo_word_match(target[target_index], source[idx][0])
            if ok:
                walk(target_index + 1, idx + 1, [*chosen, idx], used_similarity or fuzzy)

    walk(0, 0, [], False)
    # Keep only the tightest alignments; all equally tight positions survive.
    if not found:
        return []
    min_width = min(end - start for start, end, _ in found)
    return [row for row in found if row[1] - row[0] == min_width]


def spans_for_decision(text: str, row: dict) -> list[tuple[int, int, bool, bool]]:
    # matched_text may be a stale OCR/transcript snapshot; audit against the
    # reviewed KB variant first so a corrected transcript can resolve it.
    literal = str(row.get("matched_variant") or row.get("matched_text") or "").strip()
    if not literal:
        literal = str(row.get("standard_name") or "").strip()
    exact = exact_spans(text, literal)
    if exact:
        return [(start, end, False, True) for start, end in exact]
    return [(start, end, fuzzy, False) for start, end, fuzzy in aligned_spans(text, literal)]


def crosses_separator(text: str, start: int, end: int, variant: str) -> bool:
    between = text[start:end]
    first_word = (variant.split() or [""])[0].casefold()
    for match in re.finditer(r"[,;()\[\]{}]", between):
        pos = match.start()
        prefix_words = [w.casefold() for w, _, _ in words_with_spans(between[:pos])]
        if between[pos] == "(" and prefix_words == [first_word]:
            continue
        if between[pos] == "[" and pos <= len(first_word) + 1:
            continue
        if between[pos] == "," and pos > 0 and pos + 1 < len(between):
            if between[pos - 1].isdigit() and between[pos + 1].isdigit():
                continue
        if between[pos] == "," and "(" in between[:pos] and (words_with_spans(between[:pos]) or [("", 0, 0)])[0][0].casefold() == first_word:
            continue
        if between[pos] == "," and prefix_words == [first_word]:
            continue
        return True
    return False


def shared_head_expression(text: str, left: dict, right: dict,
                          left_span: tuple[int, int], right_span: tuple[int, int]) -> str | None:
    """Recognize two overlapping ingredient spans that share an explicit head.

    Handles both ``<head> X dan Y`` and ``<head> X, Y`` when the reviewed
    variants themselves share one or more leading words (e.g. Perisa sintetis /
    Perisa alami, Dinatrium inosinat / Dinatrium guanilat).
    """
    left_variant = str(left.get("matched_variant") or "").split()
    right_variant = str(right.get("matched_variant") or "").split()
    common = []
    for a, b in zip(left_variant, right_variant):
        if a.casefold() != b.casefold():
            break
        common.append(a)
    if not common:
        return None
    start = max(0, min(left_span[0], right_span[0]) - 40)
    end = min(len(text), max(left_span[1], right_span[1]) + 60)
    local = text[start:end]
    # Try the longest shared head that still leaves a branch word on both
    # variants. A shorter head is needed for nested forms such as
    # "Perisa (Sintetik, Alami)" vs "Perisa (Sintetik)".
    max_head = min(len(common), len(left_variant) - 1, len(right_variant) - 1)
    separators = r"(?:&|/|;|,|\bdan\b|\batau\b)"
    for head_length in range(max_head, 0, -1):
        head = r"\s+".join(map(re.escape, common[:head_length]))
        pattern = (rf"(?<!\w){head}\s*(?:\(\s*)?\w+(?:[\s-]+\w+){{0,3}}"
                   rf"\s*{separators}\s*\w+(?:[\s-]+\w+){{0,3}}\s*\)?(?!\w)")
        for match in re.finditer(pattern, local, re.IGNORECASE):
            expr_start, expr_end = start + match.start(), start + match.end()
            if all(expr_start <= point[0] and point[1] <= expr_end
                   for point in (left_span, right_span)):
                return match.group(0)
    return None


def context_for_missing_span(text: str, row: dict, radius: int = 55) -> str:
    """Return a nearby clue for a missing candidate, or a short transcript excerpt."""
    clues = [str(row.get("matched_text") or ""), str(row.get("matched_variant") or ""),
             str(row.get("standard_name") or "")]
    for clue in clues:
        for word, _start, _end in words_with_spans(clue):
            hits = exact_spans(text, word)
            if hits:
                start, end = hits[0]
                return text[max(0, start-radius):min(len(text), end+radius)]
    return text[:min(len(text), 240)]


def row_dicts(path: Path) -> list[dict]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["kandidat_review"] if "kandidat_review" in wb.sheetnames else wb.worksheets[0]
    headers = [str(c.value or "").strip() for c in ws[1]]
    return [dict(zip(headers, values)) for values in ws.iter_rows(min_row=2, values_only=True)]


def load_kb_phrases(path: Path) -> list[tuple[str, str]]:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    phrases = []
    for entry in doc.get("ingredients", []):
        variants = [entry.get("standard_name", ""), *entry.get("synonyms", [])]
        for phrase in variants:
            phrase = str(phrase or "").strip()
            if phrase:
                phrases.append((str(entry.get("standard_name") or ""), phrase))
    return phrases


def review_evaluation(review_path: Path, transcripts_path: Path, split_path: Path,
                      kb_path: Path, strict_gt_path: Path) -> list[dict]:
    workbook_rows = row_dicts(review_path)
    manual_overrides = {}
    workbook = load_workbook(review_path, read_only=True, data_only=True)
    try:
        if "tinjauan_manual" in workbook.sheetnames:
            ws = workbook["tinjauan_manual"]
            iterator = ws.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(iterator)]
            for values in iterator:
                manual_row = dict(zip(headers, values))
                key = (manual_row.get("nama_file"), manual_row.get("entri"), manual_row.get("matched_variant"))
                decision = str(manual_row.get("keputusan_final") or "").strip().upper()
                if decision in {"Y", "N"}:
                    manual_overrides[key] = decision
    finally:
        workbook.close()
    for row in workbook_rows:
        key = (row.get("filename"), row.get("standard_name"), row.get("matched_variant"))
        if key in manual_overrides:
            row["keputusan"] = manual_overrides[key]
    review = [r for r in workbook_rows
              if str(r.get("keputusan") or "").strip().casefold() in {"y", "ya", "yes"}]
    with split_path.open(encoding="utf-8-sig", newline="") as f:
        allowed = {r["filename"] for r in csv.DictReader(f)}
    with transcripts_path.open(encoding="utf-8-sig", newline="") as f:
        transcripts = {r["filename"]: r["ground_truth_text"] for r in csv.DictReader(f)
                       if r["filename"] in allowed}
    kb_phrases = load_kb_phrases(kb_path)
    strict_doc = json.loads(strict_gt_path.read_text(encoding="utf-8-sig"))
    by_photo: dict[str, list[dict]] = {}
    for row in review:
        filename = str(row.get("filename") or "")
        if filename in allowed and filename in transcripts:
            by_photo.setdefault(filename, []).append(row)
    proposals = []
    for filename, rows in by_photo.items():
        text = transcripts[filename]
        mapped = []
        for row in rows:
            variant = str(row.get("matched_variant") or "").strip()
            spans = exact_spans(text, variant) if variant else []
            if not spans:
                spans = aligned_spans(text, variant) if variant else []
            if not spans:
                proposals.append({"nama_file": filename, "entri": row.get("standard_name"),
                                  "matched_variant": row.get("matched_variant"),
                                  "keputusan_lama": row.get("keputusan"), "keputusan_usulan": "N",
                                  "jenis_temuan": "span_tidak_ditemukan_di_transkrip",
                                  "teks_di_sekitar_span": context_for_missing_span(text, row)})
                continue
            start, end = spans[0][0], spans[0][1]
            flags = []
            if crosses_separator(text, start, end, variant):
                flags.append("span_melintasi_koma_pemisah")
            for name, phrase in kb_phrases:
                if phrase.casefold() == variant.casefold():
                    continue
                for specific_start, specific_end in exact_spans(text, phrase):
                    if specific_start <= start and end <= specific_end and specific_end - specific_start > end - start:
                        flags.append(f"subspan_bentrok_entri_spesifik:{name}")
                        break
                if flags and flags[-1].startswith("subspan_bentrok"):
                    break
            for strict_item in strict_doc.get(filename, {}).get("ingredients", []):
                strict_variant = str(strict_item.get("matched_variant") or "")
                strict_spans = exact_spans(text, strict_variant)
                # A strict span may be identical to a lenient review span when
                # the latter aligned across an inserted word (for example,
                # review "Susu bubuk" over transcript "Susu Skim Bubuk").
                # Treat equal coverage as a conflict too when the KB entries
                # differ; strict GT already owns that exact text span.
                if any(a <= start and end <= b for a, b in strict_spans):
                    strict_name = str(strict_item.get("standard_name") or "")
                    if strict_name.casefold() != str(row.get("standard_name") or "").casefold():
                        flags.append(f"entri_salah_kalah_oleh_strict:{strict_name}")
                    break
            mapped.append((row, start, end, flags))
        shared_head_rows: dict[int, str] = {}
        for i, (row, start, end, flags) in enumerate(mapped):
            for j, (other, other_start, other_end, _other_flags) in enumerate(mapped):
                if i != j and max(start, other_start) < min(end, other_end):
                    expression = shared_head_expression(text, row, other, (start, end), (other_start, other_end))
                    if expression:
                        shared_head_rows[i] = expression
                        shared_head_rows[j] = expression
                        continue
                    context = text[max(0, min(start, other_start)-40):min(len(text), max(end, other_end)+40)]
                    note = "tumpang_tindih_Y"
                    flags.append(note)
                    break
        for i in shared_head_rows:
            row, start, end, flags = mapped[i]
            flags[:] = [flag for flag in flags if not flag.startswith(("subspan_bentrok", "entri_salah"))]
            # The shared grammatical head explains the apparent overlap; both
            # distinct ingredient decisions remain accepted as Y.
        for i, (row, start, end, flags) in enumerate(mapped):
            if flags:
                context = text[max(0, start-50):min(len(text), end+50)]
                proposals.append({"nama_file": filename, "entri": row.get("standard_name"),
                                  "matched_variant": row.get("matched_variant"),
                                  "keputusan_lama": row.get("keputusan"),
                                  "keputusan_usulan": "N" if any(f.startswith(("subspan_bentrok", "entri_salah")) for f in flags) else "TINJAU",
                                  "jenis_temuan": ";".join(dict.fromkeys(flags)),
                                  "teks_di_sekitar_span": context})
        for i, expression in shared_head_rows.items():
            row, start, end, _flags = mapped[i]
            context = text[max(0, start-50):min(len(text), end+50)]
            proposals.append({"nama_file": filename, "entri": row.get("standard_name"),
                              "matched_variant": row.get("matched_variant"),
                              "keputusan_lama": row.get("keputusan"), "keputusan_usulan": "Y",
                              "jenis_temuan": "pola_kepala_bersama_Y_dipertahankan",
                              "teks_di_sekitar_span": context})
    return proposals


def write_audited_workbook(source: Path, destination: Path, proposals: list[dict],
                           y_total: int) -> None:
    wb = load_workbook(source)
    for name in ("usulan_perubahan", "ringkasan_audit"):
        if name in wb.sheetnames:
            del wb[name]
    ws = wb.create_sheet("usulan_perubahan")
    headers = ["nama_file", "entri", "matched_variant", "keputusan_lama", "keputusan_usulan", "jenis_temuan", "teks_di_sekitar_span"]
    ws.append(headers)
    for row in proposals:
        ws.append([row.get(h, "") for h in headers])
    summary = wb.create_sheet("ringkasan_audit")
    summary.append(["jenis_temuan", "jumlah_baris"])
    type_specs = [
        ("sub-span dari frasa lebih panjang", lambda flags: any(f.startswith("subspan_bentrok") for f in flags)),
        ("salah entri", lambda flags: any(f.startswith("entri_salah") for f in flags)),
        ("awalan kelas fungsi yang dikecualikan", lambda flags: any(f.startswith("awalan_kelas_fungsi_dikecualikan") for f in flags)),
        ("span melintasi koma", lambda flags: "span_melintasi_koma_pemisah" in flags),
        ("tumpang tindih sesama Y", lambda flags: "tumpang_tindih_Y" in flags or "tumpang_tindih_Y_periksa_kepala_bersama" in flags),
        ("pola kepala bersama", lambda flags: "tumpang_tindih_Y_periksa_kepala_bersama" in flags),
        ("pola kepala bersama (Y dipertahankan)", lambda flags: "pola_kepala_bersama_Y_dipertahankan" in flags),
        ("span tidak ditemukan di transcript", lambda flags: "span_tidak_ditemukan_di_transkrip" in flags),
    ]
    for label, predicate in type_specs:
        n = sum(1 for row in proposals if predicate(str(row.get("jenis_temuan") or "").split(";")))
        summary.append([label, n])
    proposed_n = sum(1 for row in proposals if row.get("keputusan_usulan") == "N")
    missing_n = sum(1 for row in proposals if row.get("jenis_temuan") == "span_tidak_ditemukan_di_transkrip")
    eligible_n = proposed_n - missing_n
    summary.append(["Y diusulkan N (termasuk span tidak ditemukan)", proposed_n])
    summary.append(["Y otomatis diubah N (tidak manual/span hilang)", eligible_n])
    summary.append(["Y tetap setelah aturan penerapan", y_total - eligible_n])
    summary.append(["Y tinjauan overlap manual", sum(1 for row in proposals if row.get("keputusan_usulan") == "TINJAU")])
    summary.append(["Y pola kepala bersama dipertahankan", sum(1 for row in proposals
                                                                    if row.get("jenis_temuan") == "pola_kepala_bersama_Y_dipertahankan")])
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)


def run(review_path: Path, transcripts_path: Path, strict_gt_path: Path, split_path: Path) -> list[dict]:
    review = [r for r in row_dicts(review_path) if str(r.get("keputusan") or "").strip().casefold() in {"y", "ya", "yes"}]
    with split_path.open(encoding="utf-8-sig", newline="") as f:
        allowed = {r["filename"] for r in csv.DictReader(f)}
    with transcripts_path.open(encoding="utf-8-sig", newline="") as f:
        transcripts = {r["filename"]: r["ground_truth_text"] for r in csv.DictReader(f) if r["filename"] in allowed}
    gt = json.loads(strict_gt_path.read_text(encoding="utf-8-sig"))
    strict_by_photo: dict[str, list[tuple[int, int, dict]]] = {}
    for filename, doc in gt.items():
        if filename not in allowed or filename not in transcripts:
            continue
        text = transcripts[filename]
        strict_by_photo[filename] = []
        for ingredient in doc.get("ingredients", []):
            variant = str(ingredient.get("matched_variant") or "")
            spans = exact_spans(text, variant) or unordered_phrase_spans(text, variant)
            for start, end in spans:
                strict_by_photo[filename].append((start, end, ingredient))

    audited = []
    for index, row in enumerate(review):
        filename = str(row.get("filename") or "")
        if filename not in allowed or filename not in transcripts:
            continue
        text = transcripts[filename]
        spans = spans_for_decision(text, row)
        if not spans:
            audited.append({**row, "flag": "span_tidak_ditemukan", "rentang": "", "teks_span": ""})
            continue
        start, end, fuzzy, literal = spans[0]
        reasons = []
        variant = str(row.get("matched_variant") or "")
        if crosses_separator(text, start, end, variant):
            reasons.append("melintasi_koma_atau_kurung")
        decision_words = len(str(row.get("matched_variant") or "").split())
        for strict_start, strict_end, ingredient in strict_by_photo.get(filename, []):
            if (strict_start <= start and end <= strict_end and strict_end - strict_start >= end - start
                    and len(str(ingredient.get("matched_variant") or "").split()) > decision_words):
                reasons.append("konflik_entri_strict_lebih_spesifik")
                break
        if not reasons and row.get("standard_name"):
            # A Y may name the wrong KB entry even when its text span is literal,
            # e.g. full-cream milk selected for a transcript saying skim milk.
            name_phrase = str(row.get("standard_name") or "").strip()
            if name_phrase and not exact_spans(text, name_phrase) and not unordered_phrase_spans(text, name_phrase):
                reasons.append("entri_tidak_didukung_teks")
        if fuzzy or not literal:
            reasons.append("hanya_kemiripan_tidak_literal")
        window_start, window_end = max(0, start - 36), min(len(text), end + 36)
        actual = text[start:end]
        local_text = text[window_start:window_end]
        if (_is_negated_match(local_text, actual, str(row.get("matched_variant") or ""))
                or _is_negated_match(local_text, actual, actual)):
            reasons.append("konteks_negasi")
        audited.append({**row, "flag": ";".join(dict.fromkeys(reasons)) or "aman_tidak_terflag",
                        "rentang": f"{start}:{end}", "teks_span": actual})

    # Add explicit pairwise Y-span overlap flags for decisions whose estimated
    # source ranges overlap within a photo.
    by_photo: dict[str, list[int]] = {}
    for i, row in enumerate(audited):
        if row.get("rentang"):
            by_photo.setdefault(str(row.get("filename")), []).append(i)
    for indices in by_photo.values():
        for i in indices:
            a, b = map(int, audited[i]["rentang"].split(":"))
            for j in indices:
                if i == j:
                    continue
                c, d = map(int, audited[j]["rentang"].split(":"))
                if max(a, c) < min(b, d):
                    expression = shared_head_expression(
                        text, audited[i], audited[j], (a, b), (c, d)
                    )
                    if expression:
                        continue
                    old = audited[i].get("flag", "")
                    audited[i]["flag"] = ";".join(dict.fromkeys([*filter(None, old.split(";")), "tumpang_tindih_keputusan_Y"]))
                    break
    return audited


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--transcripts", type=Path, default=ROOT / "dataset/ground_truth/transcripts.csv")
    parser.add_argument("--strict-gt", type=Path, default=ROOT / "evaluation/ground_truth/evaluation_gt_strict.json")
    parser.add_argument("--split", type=Path, default=ROOT / "evaluation/splits/evaluation_set.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kb", type=Path, default=ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json")
    parser.add_argument("--workbook-copy", action="store_true", help="Buat salinan workbook dengan sheet usulan_perubahan (mode split evaluasi).")
    args = parser.parse_args()
    if args.workbook_copy:
        proposals = review_evaluation(args.review, args.transcripts, args.split, args.kb, args.strict_gt)
        y_total = sum(1 for row in row_dicts(args.review)
                      if str(row.get("keputusan") or "").strip().casefold() in {"y", "ya", "yes"})
        write_audited_workbook(args.review, args.output.with_suffix(".xlsx"), proposals, y_total)
        counts = Counter(flag for row in proposals for flag in str(row["jenis_temuan"]).split(";") if flag)
        print(json.dumps({"y_rows_flagged": len(proposals), "findings": dict(counts),
                          "workbook_copy": str(args.output.with_suffix('.xlsx'))}, ensure_ascii=False, indent=2))
        return
    rows = run(args.review, args.transcripts, args.strict_gt, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    counts = Counter(flag for row in rows for flag in str(row.get("flag", "")).split(";") if flag)
    print(json.dumps({"review_y_rows": len(rows), "flags": dict(counts), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
