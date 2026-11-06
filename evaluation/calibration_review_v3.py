"""Workbook v3: hasil lenient, perbandingan v2, dan keputusan manual yang utuh."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from openpyxl.styles import Alignment, Font, PatternFill

from evaluation import calibration_annotations as matching
from evaluation.generate_calibration_review import REPO_ROOT, STRICT_GT_PATH, json_bytes
from evaluation.generate_calibration_review_v2 import (
    build_v2_workbook, candidate_key, carry_decisions, read_previous_review,
)

V2_PATH = REPO_ROOT / "dataset/ground_truth/calibration_review_v2.xlsx"
V3_PATH = REPO_ROOT / "dataset/ground_truth/calibration_review_v3.xlsx"
SUMMARY_PATH = REPO_ROOT / "dataset/ground_truth/calibration_regeneration_v3_summary.json"


def filter_reasons(row: dict, strict_gt: dict, candidates: list[dict], before: dict | None,
                   kb: list[dict]) -> str:
    filename = row["filename"]
    if any(c["filename"] == filename and c["standard_name"] == row["standard_name"] for c in candidates):
        return "matched_variant_berubah"
    if before is None:
        return "tidak_muncul_dengan_aturan_lenient_v3"
    text = strict_gt[filename]["composition_text"]
    original = [m for m in before["occurrences"].get(filename, [])
                if m["standard_name"] == row["standard_name"]
                and m["matched_variant"] == row["matched_variant"]]
    reasons = set()
    surviving = matching.lenient_occurrences(text, kb)
    for item in original:
        actual = matching.normalize_words(text[item["start"]:item["end"]])
        expected = matching.normalize_words(row["matched_variant"])
        if any(frozenset({a, b}) in matching.FORBIDDEN_TYPO_PAIRS for a in actual for b in expected):
            reasons.add("pasangan_kimia_terlarang")
        if matching._has_phrase_boundary(text, item["start"], item["end"]):
            reasons.add("melintasi_koma_atau_kurung")
        old = matching.Occurrence(**item)
        if any(
            current.ingredient_id != old.ingredient_id and not current.negated
            and current.start <= old.start and old.end <= current.end
            and len(matching.normalize_words(current.matched_variant)) > len(expected)
            and matching._specificity_is_authorized(old, current)
            and matching._ordered_subset(tuple(expected), tuple(matching.normalize_words(current.matched_variant)))
            for current in surviving
        ):
            reasons.add("nama_bahan_lebih_spesifik")
    return "; ".join(sorted(reasons)) or "tidak_muncul_dengan_aturan_lenient_v3"


def compare_review(candidates: list[dict], previous: list[dict]) -> tuple[list[dict], dict]:
    review, continuity = carry_decisions(candidates, previous)
    active = {candidate_key(row) for row in candidates}
    previous_keys = {candidate_key(row) for row in previous}
    lost = [row for row in previous if candidate_key(row) not in active]
    new = [row for row in candidates if candidate_key(row) not in previous_keys]
    kept = [row for row in previous if candidate_key(row) in active]
    continuity.update({
        "previous_decisions": dict(Counter(row["keputusan"] or "KOSONG" for row in previous)),
        "lost_by_previous_decision": dict(Counter(row["keputusan"] or "KOSONG" for row in lost)),
        "retained_by_previous_decision": dict(Counter(row["keputusan"] or "KOSONG" for row in kept)),
        "new_candidate_total": len(new),
        "manual_approved_total": sum(row["keputusan"] == "Y" for row in previous),
        "manual_approved_filtered_total": sum(row["keputusan"] == "Y" for row in lost),
    })
    return review, continuity


def _style_table(sheet) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24465A")
    widths = {"filename": 25, "standard_name": 75, "category": 18,
              "sumber": 24, "matched_variant": 60, "potongan_teks": 120,
              "keputusan": 16, "keputusan_final": 20, "keputusan_v2": 18,
              "status_vs_v2": 30, "status_deteksi_v3": 30, "alasan_filter": 45}
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = widths.get(column[0].value, 30)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def build_v3_workbook(strict_gt: dict, candidates: list[dict], previous: list[dict],
                      review: list[dict], summary: dict):
    workbook = build_v2_workbook(strict_gt, candidates, review, summary, [])
    sheet = workbook["kandidat_review"]
    sheet["H1"] = "status_vs_v2"
    sheet["I1"] = "alasan_filter"
    for index, row in enumerate(review, 2):
        sheet.cell(index, 9, row.get("alasan_filter", ""))
    _style_table(sheet)
    active = {candidate_key(row) for row in candidates}
    # Keputusan manusia bukan hasil deteksi otomatis. Seluruh Y disimpan,
    # termasuk yang kini gagal syarat frasa atau dikalahkan bahan spesifik.
    manual = workbook.create_sheet("disetujui_manual_v2")
    fields = ["filename", "standard_name", "category", "matched_variant", "potongan_teks", "keputusan_final", "status_deteksi_v3"]
    manual.append(fields)
    for row in previous:
        if row["keputusan"] == "Y":
            manual.append([row["filename"], row["standard_name"], row["category"], row["matched_variant"],
                           row["potongan_teks"], "Y",
                           "TETAP_DI_LENIENT_V3" if candidate_key(row) in active else "TERFILTER_OTOMATIS"])
    _style_table(manual)
    lost = workbook.create_sheet("hilang_dari_v2")
    lost_fields = ["filename", "standard_name", "category", "matched_variant", "keputusan_v2", "alasan_filter", "potongan_teks"]
    lost.append(lost_fields)
    for row in review:
        if row["status_vs_v1"] == "HILANG":
            lost.append([row["filename"], row["standard_name"], row["category"], row["matched_variant"],
                         row["keputusan"], row.get("alasan_filter", ""), row["potongan_teks"]])
    _style_table(lost)
    notes = workbook["ringkasan"]
    for item in notes.iter_rows(min_row=2):
        if item[0].value == "HILANG":
            item[1].value = "Baris historis v2 yang tidak ditemukan matcher v3. Keputusan lama tetap disimpan untuk audit."
        elif item[0].value == "nama spesifik":
            item[1].value = "Lenient memprioritaskan nama lebih spesifik pada kemunculan yang sama sesuai cakupan aturan yang disetujui."
        elif item[0].value == "lenient":
            item[1].value = "Normalisasi istilah dan typo satu karakter tetap aktif; pasangan terlarang dikecualikan. Maksimal tiga kata sisipan dalam satu frasa."
    for key in ("new_candidate_total", "manual_approved_total", "manual_approved_filtered_total",
                "previous_decisions", "lost_by_previous_decision", "retained_by_previous_decision", "forbidden_typo_pairs"):
        value = summary[key]
        notes.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    notes.append(["keputusan manual", "Seluruh Y v2 tetap disimpan sebagai keputusan final di disetujui_manual_v2; TERFILTER_OTOMATIS menunjukkan aturan baru tidak lagi mendeteksinya, bukan pembatalan Y."])
    notes.append(["batas frasa", "Lenient tidak melintasi koma pemisah item, titik koma, atau kurung. Koma desimal tetap diperbolehkan."])
    return workbook


def write_review_v3(strict_gt: dict, candidates: list[dict], kb: list[dict], *, dry_run: bool = False) -> dict:
    stored = json.loads(STRICT_GT_PATH.read_text(encoding="utf-8-sig"))
    if stored != strict_gt:
        raise ValueError("Strict GT tersimpan berbeda dari hasil saat ini; mode v3 tidak boleh mengubah strict GT.")
    previous = read_previous_review(V2_PATH)
    review, continuity = compare_review(candidates, previous)
    before_path = REPO_ROOT / "evaluation/results/calibration_v3_before_occurrences.json"
    before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else None
    for row in review:
        if row["status_vs_v1"] == "HILANG":
            row["alasan_filter"] = filter_reasons(row, strict_gt, candidates, before, kb)
    exact = [ingredient for info in strict_gt.values() for ingredient in info["ingredients"]]
    summary = {
        "n_photos": len(strict_gt), "kb_ingredients": len({entry["ingredient_id"] for entry in kb}),
        "kb_variants": len(kb), "kb_sha256": hashlib.sha256(json_bytes(kb)).hexdigest(),
        "old_exact_total": len(exact), "exact_total": len(exact),
        "exact_by_category": dict(Counter(row["category"] for row in exact)),
        "candidates_by_category": dict(Counter(row["category"] for row in candidates)),
        "candidates_by_source": dict(Counter(row["sumber"] for row in candidates)), "changes_by_type": {},
        "previous_review_path": str(V2_PATH), "previous_review_sha256": hashlib.sha256(V2_PATH.read_bytes()).hexdigest(),
        "forbidden_typo_pairs": sorted(sorted(pair) for pair in matching.FORBIDDEN_TYPO_PAIRS), **continuity,
        "lost_candidates": [row for row in review if row["status_vs_v1"] == "HILANG"],
        "new_candidates": [row for row in candidates if candidate_key(row) not in {candidate_key(old) for old in previous}],
    }
    if not dry_run:
        if V3_PATH.exists() or SUMMARY_PATH.exists():
            raise FileExistsError("Output v3 sudah ada. Arsipkan output tersebut sebelum regenerasi agar keputusan manual tidak tertimpa.")
        workbook = build_v3_workbook(strict_gt, candidates, previous, review, summary)
        workbook.save(V3_PATH)
        SUMMARY_PATH.write_bytes(json_bytes(summary))
        print(f"Review v3: {V3_PATH}")
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"lost_candidates", "new_candidates", "carried_keys", "lost_keys"}}, ensure_ascii=False, indent=2))
    return summary
