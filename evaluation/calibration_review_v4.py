"""Review v4: kandidat aktual, penandaan taksonomi, dan seluruh Y manual v2."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from evaluation import calibration_annotations as matching
from evaluation.calibration_review_v3 import _style_table, filter_reasons
from evaluation.generate_calibration_review import REPO_ROOT, STRICT_GT_PATH, json_bytes
from evaluation.generate_calibration_review_v2 import (
    build_v2_workbook, candidate_key, carry_decisions, read_previous_review,
)

V2_PATH = REPO_ROOT / "dataset/ground_truth/calibration_review_v2.xlsx"
V4_PATH = REPO_ROOT / "dataset/ground_truth/calibration_review_v4.xlsx"
SUMMARY_PATH = REPO_ROOT / "dataset/ground_truth/calibration_regeneration_v4_summary.json"
MANUAL_SOURCE = "disetujui_manual_v2"


def prepare_review(candidates: list[dict], previous: list[dict], kb: list[dict]):
    """Y yang terfilter tetap menjadi keputusan aktif, tanpa mengubah matcher."""
    automatic_keys = {candidate_key(row) for row in candidates}
    variants = {(entry["standard_name"], entry["name_variant"]): entry for entry in kb}
    active = [dict(row, status_deteksi_v4="OTOMATIS") for row in candidates]
    restored = []
    for old in previous:
        if old["keputusan"] != "Y" or candidate_key(old) in automatic_keys:
            continue
        entry = variants.get((old["standard_name"], old["matched_variant"]))
        if entry is None or entry["category"] != old["category"]:
            raise ValueError(f"Keputusan Y lama tidak identik dengan KB saat ini: {candidate_key(old)}")
        row = dict(old, ingredient_id=entry["ingredient_id"], sumber=MANUAL_SOURCE,
                   matched_text="", relasi_taksonomi=[], status_deteksi_v4="DIPERTAHANKAN_MANUAL")
        active.append(row)
        restored.append(row)
    review, continuity = carry_decisions(active, previous)
    active_review = [row for row in review if row["status_vs_v1"] != "HILANG"]
    archived = [row for row in review if row["status_vs_v1"] == "HILANG"]
    previous_keys = {candidate_key(row) for row in previous}
    continuity.update({
        "workbook_row_total": len(active_review), "archive_row_total": len(archived),
        "automatic_candidate_total": len(candidates), "manual_restored_total": len(restored),
        "automatic_filtered_total": sum(candidate_key(row) not in automatic_keys for row in previous),
        "new_candidate_total": sum(candidate_key(row) not in previous_keys for row in active_review),
        "carried_y_total": sum(row["keputusan"] == "Y" for row in active_review),
        "carried_n_total": sum(row["keputusan"] == "N" for row in active_review),
        "previous_decisions": dict(Counter(row["keputusan"] or "KOSONG" for row in previous)),
        "taxonomy_candidate_total": sum(row["sumber"] == matching.TAXONOMY_SOURCE for row in active_review),
        "taxonomy_by_decision": dict(Counter(row["keputusan"] or "KOSONG" for row in active_review
                                             if row["sumber"] == matching.TAXONOMY_SOURCE)),
    })
    return active, active_review, archived, continuity


def build_v4_workbook(strict_gt: dict, active: list[dict], review: list[dict],
                      archived: list[dict], filtered: list[dict], summary: dict):
    workbook = build_v2_workbook(strict_gt, active, review, summary, [])
    sheet = workbook["kandidat_review"]
    sheet["H1"] = "status_vs_v2"
    for column, label in enumerate(("status_deteksi_v4", "alasan_filter", "relasi_ambigu"), 9):
        sheet.cell(1, column, label)
    for index, row in enumerate(review, 2):
        sheet.cell(index, 9, row["status_deteksi_v4"])
        sheet.cell(index, 10, row.get("alasan_filter", ""))
        relations = row.get("relasi_taksonomi", [])
        sheet.cell(index, 11, "\n".join(sorted({
            f"{detail['bahan_umum']} -> {detail['bahan_spesifik']}: {detail['matched_text']}"
            for detail in relations
        })))
    _style_table(sheet)
    sheet.column_dimensions["D"].width = 46
    sheet.column_dimensions["I"].width = 30
    sheet.column_dimensions["K"].width = 90

    manual = workbook.create_sheet("disetujui_manual_v2")
    manual.append(["filename", "standard_name", "category", "matched_variant", "keputusan_final",
                   "status_deteksi_v4", "alasan_filter"])
    for row in review:
        if row["keputusan"] == "Y":
            manual.append([row["filename"], row["standard_name"], row["category"], row["matched_variant"],
                           "Y", row["status_deteksi_v4"], row.get("alasan_filter", "")])
    _style_table(manual)

    for title, rows in (("arsip_nonaktif_v2", archived), ("terfilter_otomatis", filtered)):
        sheet = workbook.create_sheet(title)
        sheet.append(["filename", "standard_name", "category", "matched_variant", "keputusan_v2",
                      "status_v4", "alasan_filter", "potongan_teks"])
        for row in rows:
            sheet.append([row["filename"], row["standard_name"], row["category"], row["matched_variant"],
                          row["keputusan"], "DIPERTAHANKAN_MANUAL" if row["keputusan"] == "Y" else "NONAKTIF",
                          row.get("alasan_filter", ""), row["potongan_teks"]])
        _style_table(sheet)

    notes = workbook["ringkasan"]
    replacements = {
        "HILANG": "Baris nonaktif v2 tersedia di arsip_nonaktif_v2; semua Y lama tetap aktif di kandidat_review.",
        "lenient": "Typo satu karakter tetap aktif kecuali 10 pasangan terlarang. Kode berangka harus persis. Maksimal tiga kata sisipan tanpa melintasi koma/kurung.",
        "nama spesifik": "Longest-match-wins lenient HANYA untuk Minyak kelapa -> Minyak kelapa sawit. Relasi lain tidak menekan kandidat; ditandai untuk review.",
    }
    for row in notes.iter_rows(min_row=2):
        if row[0].value in replacements:
            row[1].value = replacements[row[0].value]
    for key in ("automatic_candidate_total", "manual_restored_total", "carried_y_total", "carried_n_total",
                "new_candidate_total", "taxonomy_candidate_total", "taxonomy_by_decision",
                "archive_row_total", "automatic_filtered_total", "forbidden_typo_pairs"):
        value = summary[key]
        notes.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    notes.append(["keputusan manusia", "Y v2 yang gagal filter otomatis tetap aktif sebagai DIPERTAHANKAN_MANUAL sesuai instruksi pengguna; matcher tidak dibuat lebih longgar."])
    notes.append(["taksonomi", "ambigu_taksonomi_tunggu_ahli_gizi hanya menandai relasi audit yang ditemukan dalam frasa nyata. Penandaan tidak mengganti keputusan Y/N dan tidak menetapkan taksonomi klinis."])
    notes.append(["merge", "Merge hanya membaca kandidat_review dan wajib menolak keputusan kosong. Arsip nonaktif tidak digabungkan."])
    return workbook


def write_review_v4(strict_gt: dict, candidates: list[dict], kb: list[dict], *, dry_run: bool = False):
    if json.loads(STRICT_GT_PATH.read_text(encoding="utf-8-sig")) != strict_gt:
        raise ValueError("Strict GT berubah; mode v4 tidak boleh menimpa ground truth mentah.")
    source_hash = hashlib.sha256(V2_PATH.read_bytes()).hexdigest()
    previous = read_previous_review(V2_PATH)
    if any(row["filename"] not in strict_gt for row in previous):
        raise ValueError("Review sebelumnya memiliki filename di luar split kalibrasi.")
    active, review, archived, continuity = prepare_review(candidates, previous, kb)
    automatic_keys = {candidate_key(row) for row in candidates}
    before_path = REPO_ROOT / "evaluation/results/calibration_v3_before_occurrences.json"
    before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else None
    filtered = [dict(row) for row in previous if candidate_key(row) not in automatic_keys]
    reasons = {}
    for row in filtered:
        row["alasan_filter"] = filter_reasons(row, strict_gt, candidates, before, kb)
        reasons[candidate_key(row)] = row["alasan_filter"]
    for row in review + archived:
        row["alasan_filter"] = reasons.get(candidate_key(row), "")
    exact = [ingredient for info in strict_gt.values() for ingredient in info["ingredients"]]
    summary = {
        "version": "v4", "n_photos": len(strict_gt), "kb_ingredients": len({entry["ingredient_id"] for entry in kb}),
        "kb_variants": len(kb), "kb_sha256": hashlib.sha256(json_bytes(kb)).hexdigest(),
        "old_exact_total": len(exact), "exact_total": len(exact),
        "exact_by_category": dict(Counter(row["category"] for row in exact)),
        "candidates_by_category": dict(Counter(row["category"] for row in active)),
        "candidates_by_source": dict(Counter(row["sumber"] for row in active)), "changes_by_type": {},
        "previous_review_path": str(V2_PATH), "previous_review_sha256": source_hash,
        "forbidden_typo_pairs": sorted(sorted(pair) for pair in matching.FORBIDDEN_TYPO_PAIRS),
        "numeric_codes_exact_only": True, "specificity_scope": "Minyak kelapa -> Minyak kelapa sawit",
        "taxonomy_review_relations": len(matching.TAXONOMY_REVIEW_PAIRS), **continuity,
        "active_candidates": review, "archived_candidates": archived, "filtered_automatic_candidates": filtered,
    }
    if not dry_run:
        if V4_PATH.exists() or SUMMARY_PATH.exists():
            raise FileExistsError("Output v4 sudah ada; arsipkan dahulu agar keputusan manual tidak tertimpa.")
        workbook = build_v4_workbook(strict_gt, active, review, archived, filtered, summary)
        if hashlib.sha256(V2_PATH.read_bytes()).hexdigest() != source_hash:
            raise ValueError("Workbook sumber berubah selama regenerasi; jalankan ulang dari sumber terbaru.")
        workbook.save(V4_PATH)
        workbook.close()
        SUMMARY_PATH.write_bytes(json_bytes(summary))
        print(f"Review v4: {V4_PATH}")
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"active_candidates", "archived_candidates", "filtered_automatic_candidates", "carried_keys", "lost_keys"}}, ensure_ascii=False, indent=2))
    return summary
