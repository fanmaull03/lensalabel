"""Create a reviewed-workbook copy with only unambiguous audit N proposals applied."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from audit_review_decisions import review_evaluation, row_dicts

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation/ground_truth/evaluation_review.xlsx"
DESTINATION = ROOT / "evaluation/ground_truth/evaluation_review_applied.xlsx"
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
KB = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
STRICT_GT = ROOT / "evaluation/ground_truth/evaluation_gt_strict.json"


def main() -> None:
    proposals = review_evaluation(SOURCE, TRANSCRIPTS, SPLIT, KB, STRICT_GT)
    source_rows = row_dicts(SOURCE)
    wb = load_workbook(SOURCE)
    ws = wb["kandidat_review"]
    headers = [str(cell.value or "").strip() for cell in ws[1]]
    positions = {name: index + 1 for index, name in enumerate(headers)}
    required = {"filename", "standard_name", "matched_variant", "keputusan"}
    if required - positions.keys():
        raise ValueError(f"Kolom workbook tidak lengkap: {sorted(required - positions.keys())}")
    row_positions = {}
    for excel_row, row in enumerate(source_rows, start=2):
        key = (row.get("filename"), row.get("standard_name"), row.get("matched_variant"))
        if key in row_positions:
            raise ValueError(f"Kunci review duplikat: {key}")
        row_positions[key] = excel_row

    changed = 0
    manual_rows = []
    for proposal in proposals:
        key = (proposal.get("nama_file"), proposal.get("entri"), proposal.get("matched_variant"))
        finding = str(proposal.get("jenis_temuan") or "")
        decision = str(proposal.get("keputusan_usulan") or "")
        if finding == "span_tidak_ditemukan_di_transkrip":
            reason = "Span tidak ditemukan di transkrip; keputusan dibiarkan apa adanya."
            manual_rows.append({**proposal, "alasan_penandaan": reason})
            continue
        if decision == "TINJAU":
            manual_rows.append({**proposal, "alasan_penandaan": "Overlap perlu tinjauan manual; keputusan tidak diubah."})
            continue
        if decision == "Y" and finding == "pola_kepala_bersama_Y_dipertahankan":
            manual_rows.append({**proposal, "alasan_penandaan": "Pola kepala bersama terdeteksi; Y dipertahankan."})
            continue
        if decision == "N":
            excel_row = row_positions.get(key)
            if excel_row is None:
                raise KeyError(f"Baris review tidak ditemukan untuk usulan: {key}")
            ws.cell(excel_row, positions["keputusan"]).value = "N"
            changed += 1

    if len([r for r in manual_rows if r["jenis_temuan"] == "span_tidak_ditemukan_di_transkrip"]) != 4:
        raise AssertionError("Jumlah kasus span tidak ditemukan berubah; workbook tidak ditulis.")
    manual_count = sum(r["keputusan_usulan"] == "TINJAU" for r in manual_rows)
    shared_count = sum(r["keputusan_usulan"] == "Y" for r in manual_rows)
    if (manual_count, shared_count) != (5, 2):
        raise AssertionError(f"Expected 5 manual overlap + 2 shared-head Y, got {manual_count} + {shared_count}.")

    if "tinjauan_manual" in wb.sheetnames:
        del wb["tinjauan_manual"]
    manual = wb.create_sheet("tinjauan_manual")
    manual.append(["nama_file", "entri", "matched_variant", "keputusan_lama", "keputusan_usulan",
                   "jenis_temuan", "alasan_penandaan", "teks_di_sekitar_span", "keputusan_final"])
    for row in manual_rows:
        manual.append([row.get(key, "") for key in ("nama_file", "entri", "matched_variant", "keputusan_lama",
                                                       "keputusan_usulan", "jenis_temuan", "alasan_penandaan",
                                                       "teks_di_sekitar_span")]
                      + ["Y" if row.get("jenis_temuan") == "pola_kepala_bersama_Y_dipertahankan" else ""])
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    wb.save(DESTINATION)
    print(f"Tersimpan: {DESTINATION}")
    print(f"Usulan N diterapkan: {changed}; tinjauan_manual: {len(manual_rows)} "
          f"(5 overlap manual + 2 kepala bersama Y; 4 span tidak ditemukan).")


if __name__ == "__main__":
    main()
