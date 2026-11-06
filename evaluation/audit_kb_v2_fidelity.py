"""Compare every Phase 2 KB lineage with the signed expert table."""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document
from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation/results/kb_v2_phase2"
CATEGORIES = {"Aman": "aman", "Perlu Perhatian": "perhatian", "Hindari": "hindari"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path, required=True)
    args = parser.parse_args()
    doc = Document(args.docx)
    table = doc.tables[1]
    if len(table.rows) != 241 or len(table.columns) != 8:
        raise ValueError("Bentuk tabel ahli berubah")
    source_rows = {}
    for row in table.rows[1:]:
        cells = [cell.text.strip() for cell in row.cells]
        old_no = int(cells[0])
        correction = cells[4] if cells[6] == "Setuju" else cells[6]
        source_rows[old_no] = {"name": cells[1], "category": CATEGORIES[correction]}

    payload = json.loads((OUT / "kb_v2_review.json").read_text(encoding="utf-8"))
    mapping = json.loads((OUT / "old_to_new_mapping.json").read_text(encoding="utf-8"))
    by_id = {item["new_entry_id"]: item for item in payload["ingredients"]}
    by_old = defaultdict(list)
    for row in mapping:
        if row["old_no"] is not None:
            by_old[row["old_no"]].append(row)
    if set(by_old) != set(source_rows) or len(by_old) != 240:
        raise ValueError("Pemetaan old_no tidak mencakup tabel ahli")
    results = []
    for old_no in range(1, 241):
        expert = source_rows[old_no]
        mapped = by_old[old_no]
        got = sorted({by_id[row["new_entry_id"]]["category"] for row in mapped})
        changed_structure = len(mapped) > 1 or any(row["jenis_perubahan"] == "merged" for row in mapped)
        if got == [expert["category"]]:
            status = "SESUAI"
        elif changed_structure:
            status = "PENGECUALIAN_STRUKTURAL_PERLU_REVIEW"
        else:
            status = "SELISIH_TIDAK_DIIZINKAN"
        results.append({"old_no": old_no, "nama_docx": expert["name"],
                        "kategori_docx": expert["category"],
                        "new_entry_id": " | ".join(row["new_entry_id"] for row in mapped),
                        "kategori_kb_v2": " | ".join(got),
                        "jenis_perubahan": " | ".join(row["jenis_perubahan"] for row in mapped),
                        "status": status})
    random_rows = sorted(random.Random(42).sample(results, 20), key=lambda row: row["old_no"])
    if any(row["status"] == "SELISIH_TIDAK_DIIZINKAN" for row in results):
        raise ValueError("Ada selisih kategori yang tidak diizinkan")
    summary = {"checked": len(results), "status_counts": dict(Counter(row["status"] for row in results)),
               "sample_seed": 42, "sample_old_numbers": [row["old_no"] for row in random_rows],
               "all_differences": [row for row in results if row["status"] != "SESUAI"]}
    OUT.mkdir(parents=True, exist_ok=True)
    headers = list(results[0])
    for name, rows in (("fidelity_all_240.csv", results), ("fidelity_sample20.csv", random_rows)):
        with (OUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
    wb = Workbook()
    wb.remove(wb.active)
    for title, data in (("semua_240", results), ("sampel_20_seed42", random_rows),
                        ("selisih", summary["all_differences"])):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for row in data:
            ws.append([row[key] for key in headers])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.save(OUT / "fidelity_audit.xlsx")
    (OUT / "fidelity_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
