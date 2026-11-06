"""Merge strict and reviewed evaluation GT with explicit span resolution rules."""
from __future__ import annotations

import copy
import csv
import json
import argparse
import re
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

try:
    from audit_review_decisions import shared_head_expression, exact_spans, aligned_spans
except ModuleNotFoundError:  # package import from pytest/repo root
    from evaluation.audit_review_decisions import shared_head_expression, exact_spans, aligned_spans

ROOT = Path(__file__).resolve().parents[1]
STRICT_PATH = ROOT / "evaluation/ground_truth/evaluation_gt_strict.json"
REVIEW_PATH = ROOT / "evaluation/ground_truth/evaluation_review_applied_v2.xlsx"
KB_PATH = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
TRANSCRIPTS_PATH = ROOT / "dataset/ground_truth/transcripts.csv"
SPLIT_PATH = ROOT / "evaluation/splits/evaluation_set.csv"
OUTPUT_PATH = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
RESOLUTION_PATH = ROOT / "evaluation/results/gt_merge_resolution.csv"
CALIBRATION_GT_PATH = ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json"
CALIBRATION_SPLIT_PATH = ROOT / "evaluation/splits/calibration_set.csv"


def read_review(path: Path) -> list[dict]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    pending = []
    try:
        sheet = workbook["kandidat_review"]
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator)
        rows = [dict(zip(headers, values)) for values in iterator if any(v is not None for v in values)]
        overrides = {}
        if "tinjauan_manual" in workbook.sheetnames:
            manual_iterator = workbook["tinjauan_manual"].iter_rows(values_only=True)
            manual_headers = next(manual_iterator)
            manual_rows = [dict(zip(manual_headers, values)) for values in manual_iterator
                           if any(v is not None for v in values)]
            for index, manual_row in enumerate(manual_rows, 2):
                key = (manual_row.get("nama_file"), manual_row.get("entri"), manual_row.get("matched_variant"))
                decision = str(manual_row.get("keputusan_final") or "").strip().upper()
                if decision not in {"Y", "N"}:
                    pending.append(index)
                else:
                    overrides[key] = decision
    finally:
        workbook.close()
    if pending:
        raise ValueError(f"Keputusan tinjauan_manual belum final pada baris: {pending}")
    for row in rows:
        key = (row.get("filename"), row.get("standard_name"), row.get("matched_variant"))
        if key in overrides:
            row["keputusan"] = overrides[key]
    unresolved = [(i + 2, row.get("keputusan")) for i, row in enumerate(rows)
                  if str(row.get("keputusan") or "").strip().upper() not in {"Y", "N"}]
    if unresolved:
        raise ValueError(f"Keputusan review belum Y/N: {unresolved[:20]}")
    return rows


def find_spans(text: str, variant: str) -> list[tuple[int, int]]:
    exact = exact_spans(text, variant)
    if exact:
        return exact
    return [(start, end) for start, end, _fuzzy in aligned_spans(text, variant)]


def build(strict: dict, reviews: list[dict], kb_doc: dict, texts: dict[str, str], allowed: set[str]) -> dict:
    kb_rows = []
    used_ids: set[int] = set()
    next_id = max((int(value) for entry in kb_doc["ingredients"]
                   for value in entry.get("old_entry_ids", [])), default=0) + 1
    for entry in kb_doc["ingredients"]:
        iid = next((int(value) for value in entry.get("old_entry_ids", [])
                    if int(value) not in used_ids), None)
        if iid is None:
            while next_id in used_ids:
                next_id += 1
            iid = next_id
            next_id += 1
        used_ids.add(iid)
        for variant in [entry["standard_name"], *entry.get("synonyms", [])]:
            kb_rows.append({"ingredient_id": iid, "standard_name": entry["standard_name"],
                            "category": entry["category"], "name_variant": variant})
    by_variant = {(row["standard_name"], row["name_variant"]): row for row in kb_rows}
    final = copy.deepcopy(strict)
    for row in reviews:
        filename = str(row.get("filename") or "")
        if filename not in allowed:
            continue
        if str(row.get("keputusan")).strip().upper() != "Y":
            continue
        name = str(row.get("standard_name") or "").strip()
        variant = str(row.get("matched_variant") or name).strip()
        entry = by_variant.get((name, variant))
        if entry is None:
            raise ValueError(f"Keputusan Y tidak cocok dengan KB v2: {filename}, {name}, {variant}")
        if filename not in final:
            raise KeyError(f"Strict GT tidak memuat {filename}")
        items = final[filename].setdefault("ingredients", [])
        if any(item["standard_name"] == name for item in items):
            continue
        items.append({"ingredient_id": entry["ingredient_id"], "standard_name": name,
                      "category": entry["category"], "matched_variant": variant,
                      "annotation_source": "review_manual", "review_source": row.get("sumber", "")})
    return final


def _is_strict(item: dict) -> bool:
    return str(item.get("annotation_source") or "").casefold() != "review_manual"


def _span_label(text: str, span: tuple[int, int]) -> str:
    start, end = span
    return f"[{start}:{end}] {text[start:end]}"


def resolve_spans(documents: dict, texts: dict[str, str], allowed: set[str], split_name: str) -> tuple[dict, list[dict], list[dict]]:
    """Apply R1-R3 and the recorded datar_049 manual decision."""
    resolved = copy.deepcopy(documents)
    resolutions: list[dict] = []
    missing: list[dict] = []
    for filename in sorted(allowed):
        if filename not in resolved or filename not in texts:
            continue
        text = texts[filename]
        items = resolved[filename].get("ingredients", [])
        located = []
        for item_index, item in enumerate(items):
            variant = str(item.get("matched_variant") or item.get("standard_name") or "")
            spans = find_spans(text, variant)
            if not spans:
                missing.append({"split": split_name, "foto": filename,
                                "entri": item.get("standard_name"), "variant": variant})
                continue
            for start, end in spans:
                located.append({"index": item_index, "item": item, "span": (start, end)})

        dropped: set[int] = set()
        r1_covered: dict[int, set[tuple[int, int]]] = {}
        r1_rows_by_index: dict[int, list[dict]] = {}
        seen_pairs: set[tuple] = set()
        for left_index, left in enumerate(located):
            for right in located[left_index + 1:]:
                if left["index"] == right["index"]:
                    continue
                left_name = str(left["item"].get("standard_name") or "")
                right_name = str(right["item"].get("standard_name") or "")
                if left_name.casefold() == right_name.casefold():
                    continue
                a, b = left["span"]
                c, d = right["span"]
                if max(a, c) >= min(b, d):
                    continue

                left_item, right_item = left["item"], right["item"]
                left_source, right_source = ("strict" if _is_strict(left_item) else "Y",
                                             "strict" if _is_strict(right_item) else "Y")
                common = {"split": split_name, "foto": filename,
                          "entri_A": left_name, "span_A": _span_label(text, left["span"]),
                          "entri_B": right_name, "span_B": _span_label(text, right["span"]),
                          "teks_sekitar": text[max(0, min(a, c)-60):min(len(text), max(b, d)+60)]}
                pair_key = (left["index"], right["index"], left["span"], right["span"])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                expression = shared_head_expression(text, left_item, right_item, left["span"], right["span"])
                if expression:
                    resolutions.append({**common, "aturan": "R3", "tindakan": "PERTAHANKAN_KEDUANYA"})
                    continue

                if (a, b) == (c, d):
                    if left_source == "strict" and right_source == "Y":
                        dropped.add(right["index"])
                        action = "PERTAHANKAN_A_STRICT_BUANG_B_Y"
                    elif right_source == "strict" and left_source == "Y":
                        dropped.add(left["index"])
                        action = "BUANG_A_Y_PERTAHANKAN_B_STRICT"
                    else:
                        resolutions.append({**common, "aturan": "R4", "tindakan": "MENUNGGU_KEPUTUSAN_KARENA_TIDAK_ADA_PEMENANG_STRICT"})
                        continue
                    resolutions.append({**common, "aturan": "R2", "tindakan": action})
                    continue

                # Expert-approved case: the head "Tepung Beras" identifies
                # the ingredient; the nested grain descriptor is not a second
                # ingredient. Apply to Merah and Coklat spans on datar_049.
                if split_name == "evaluasi" and filename == "datar_049.jpeg":
                    left_text, right_text = text[a:b], text[c:d]
                    head_left = re.fullmatch(r"Tepung\s+Beras", left_text, re.IGNORECASE)
                    head_right = re.fullmatch(r"Tepung\s+Beras", right_text, re.IGNORECASE)
                    grain_left = re.fullmatch(r"Beras\s+(?:Merah|Coklat|Cokelat)", left_text, re.IGNORECASE)
                    grain_right = re.fullmatch(r"Beras\s+(?:Merah|Coklat|Cokelat)", right_text, re.IGNORECASE)
                    if (head_left and grain_right) or (head_right and grain_left):
                        drop_index = right["index"] if head_left else left["index"]
                        dropped.add(drop_index)
                        resolutions.append({**common, "aturan": "R4", "tindakan": "KEPUTUSAN_MANUAL_PERTAHANKAN_TEPUNG_BERAS_BUANG_BERAS_DESCRIPTOR",
                                            "alasan_manual": "Kata inti frasa Tepung Beras Merah/Coklat adalah tepung; pemetaan mengikuti entri Tepung beras."})
                        continue

                if a <= c and d <= b:
                    target = right
                    action = "PERTAHANKAN_A_BUANG_B"
                elif c <= a and b <= d:
                    target = left
                    action = "BUANG_A_PERTAHANKAN_B"
                else:
                    resolutions.append({**common, "aturan": "R4", "tindakan": "MENUNGGU_KEPUTUSAN_OVERLAP_PARSIAL"})
                    continue
                r1_covered.setdefault(target["index"], set()).add(target["span"])
                resolution = {**common, "aturan": "R1", "tindakan": action,
                              "_r1_target": target["index"]}
                r1_rows_by_index.setdefault(target["index"], []).append(resolution)
                resolutions.append(resolution)

        # Resolution rows describe overlapping occurrences, while GT items are
        # photo+entry identities. Remove an item only when every occurrence of
        # its annotated variant is covered; a standalone occurrence preserves it.
        spans_by_index: dict[int, set[tuple[int, int]]] = {}
        for span_row in located:
            spans_by_index.setdefault(span_row["index"], set()).add(span_row["span"])
        for index, covered in r1_covered.items():
            all_spans = spans_by_index.get(index, set())
            if all_spans and all_spans.issubset(covered):
                dropped.add(index)
                for row in r1_rows_by_index[index]:
                    row["_r1_dropped"] = (filename, index)
            else:
                for row in r1_rows_by_index[index]:
                    row["tindakan"] += "_ENTRI_DIPERTAHANKAN_KARENA_SPAN_INDEPENDEN"
                    row["span_independen"] = " | ".join(_span_label(text, span) for span in sorted(all_spans - covered))

        if dropped:
            resolved[filename]["ingredients"] = [item for index, item in enumerate(items) if index not in dropped]
    return resolved, resolutions, missing


def write_resolutions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["split", "foto", "entri_A", "span_A", "entri_B", "span_B", "aturan", "tindakan", "span_independen", "teks_sekitar", "alasan_manual"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-audit-only", action="store_true",
                        help="Audit calibration v2 and write resolution CSV; never writes evaluation GT.")
    args = parser.parse_args()
    with SPLIT_PATH.open(encoding="utf-8-sig", newline="") as stream:
        split_rows = list(csv.DictReader(stream))
    allowed = {row["filename"] for row in split_rows}
    kb_doc = json.loads(KB_PATH.read_text(encoding="utf-8-sig"))
    with TRANSCRIPTS_PATH.open(encoding="utf-8-sig", newline="") as stream:
        texts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)
                 if row["filename"] in allowed}
    if set(texts) != allowed:
        raise ValueError("Transcript tidak lengkap untuk evaluation_set.csv.")
    if args.calibration_audit_only:
        calibration_split = list(csv.DictReader(CALIBRATION_SPLIT_PATH.open(encoding="utf-8-sig", newline="")))
        calibration_allowed = {row["filename"] for row in calibration_split}
        calibration_gt = json.loads(CALIBRATION_GT_PATH.read_text(encoding="utf-8-sig"))
        count = sum(len(row.get("ingredients", [])) for row in calibration_gt.values())
        if count != 387:
            raise ValueError(f"GT kalibrasi berubah; expected 387 item, found {count}.")
        calibration_texts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(
            TRANSCRIPTS_PATH.open(encoding="utf-8-sig", newline="")) if row["filename"] in calibration_allowed}
        _, resolutions, missing = resolve_spans(calibration_gt, calibration_texts, calibration_allowed, "kalibrasi")
        write_resolutions(RESOLUTION_PATH, resolutions)
        print(json.dumps({"split": "kalibrasi", "items": count,
                          "resolution_counts": dict(Counter(row["aturan"] for row in resolutions)),
                          "unresolved_R4": sum(row["aturan"] == "R4" for row in resolutions),
                          "missing_spans": len(missing), "resolution_csv": str(RESOLUTION_PATH)},
                         ensure_ascii=False, indent=2))
        return

    strict = json.loads(STRICT_PATH.read_text(encoding="utf-8-sig"))
    if sum(len(row.get("ingredients", [])) for row in strict.values()) != 1439:
        raise ValueError("Jumlah GT strict berubah; expected 1439 item.")
    reviews = read_review(REVIEW_PATH)
    final = build(strict, reviews, kb_doc, texts, allowed)
    final, eval_resolutions, eval_missing = resolve_spans(final, texts, allowed, "evaluasi")

    calibration_split = list(csv.DictReader(CALIBRATION_SPLIT_PATH.open(encoding="utf-8-sig", newline="")))
    calibration_allowed = {row["filename"] for row in calibration_split}
    calibration_gt = json.loads(CALIBRATION_GT_PATH.read_text(encoding="utf-8-sig"))
    calibration_texts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(
        TRANSCRIPTS_PATH.open(encoding="utf-8-sig", newline="")) if row["filename"] in calibration_allowed}
    _, calibration_resolutions, calibration_missing = resolve_spans(
        calibration_gt, calibration_texts, calibration_allowed, "kalibrasi")
    all_resolutions = [*eval_resolutions, *calibration_resolutions]
    write_resolutions(RESOLUTION_PATH, all_resolutions)

    pending = [row for row in eval_resolutions if row["aturan"] == "R4" and row["tindakan"].startswith("MENUNGGU")]
    if pending:
        print(json.dumps({"evaluation_gt_written": False,
                          "evaluation_R4_pending": len(pending),
                          "evaluation_missing_spans": len(eval_missing),
                          "calibration_resolution_counts": dict(Counter(row["aturan"] for row in calibration_resolutions)),
                          "calibration_R4_pending": sum(row["aturan"] == "R4" for row in calibration_resolutions),
                          "resolution_csv": str(RESOLUTION_PATH)}, ensure_ascii=False, indent=2))
        return

    archive = ROOT / "archive/evaluation_gt_final_inputs"
    archive.mkdir(parents=True, exist_ok=True)
    for source in (STRICT_PATH, REVIEW_PATH, KB_PATH, TRANSCRIPTS_PATH, SPLIT_PATH):
        destination = archive / source.name
        if not destination.exists():
            destination.write_bytes(source.read_bytes())
    OUTPUT_PATH.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    categories = Counter(item["category"] for doc in final.values() for item in doc.get("ingredients", []))
    conditions = Counter()
    condition_by_file = {row["filename"]: row["category"] for row in split_rows}
    for filename, doc in final.items():
        conditions[condition_by_file.get(filename, "tidak_diketahui")] += len(doc.get("ingredients", []))
    print(json.dumps({"output": str(OUTPUT_PATH), "photos": len(final),
                      "total_items": sum(len(doc.get("ingredients", [])) for doc in final.values()),
                      "by_category": dict(categories), "by_condition": dict(conditions),
                      "evaluation_resolution_counts": dict(Counter(row["aturan"] for row in eval_resolutions)),
                      "r1_items_discarded": len({row["_r1_dropped"] for row in eval_resolutions if row.get("_r1_dropped")}),
                      "calibration_resolution_counts": dict(Counter(row["aturan"] for row in calibration_resolutions)),
                      "calibration_R4_pending": sum(row["aturan"] == "R4" for row in calibration_resolutions),
                      "resolution_csv": str(RESOLUTION_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
