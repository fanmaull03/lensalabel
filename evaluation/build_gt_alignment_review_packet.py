"""Create a focused expert-review workbook for ambiguous KB v2 GT mappings."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
GT_PATH = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
KB_PATH = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
SPLIT_PATH = ROOT / "evaluation/splits/evaluation_set.csv"
OUT_DIR = ROOT / "evaluation/results/gt_v2_alignment"
OUT_PATH = OUT_DIR / "validasi_pemetaan_gt_ke_kb_v2.xlsx"

DIRECT_MAPPINGS = (
    {"nama_gt_lama": "Gula pasir murni", "target_id": "v2-147", "alasan": "Alias KB v2 memuat nama GT secara persis."},
    {"nama_gt_lama": "Sukrosa", "target_id": "v2-147", "alasan": "Alias KB v2 memuat nama GT secara persis."},
    {"nama_gt_lama": "Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum", "target_id": "v2-147", "alasan": "Alias KB v2 memuat nama GT secara persis."},
    {"nama_gt_lama": "Natrium karboksimetil selulosa (Na-CMC)", "target_id": "v2-206", "alasan": "Alias KB v2 memuat Natrium karboksimetil selulosa dan Na-CMC."},
    {"nama_gt_lama": "Metil selulosa / Karboksi metil selulosa", "target_id": "v2-206", "alasan": "Alias KB v2 memuat nama GT secara persis."},
)

AMBIGUOUS_CASES = {
    "Margarin (mengandung whey/susu)": (
        "v2-028a", "v2-028b",
        "Pilih berdasarkan apakah label secara eksplisit menyatakan margarin mengandung susu, whey, atau padatan susu.",
    ),
    "Licorice": (
        "v2-234a", "v2-234b",
        "Pilih hanya jika teks label mendukung ekstrak licorice atau permen licorice. Bila tidak, pilih TIDAK_DAPAT_DITETAPKAN.",
    ),
}

HEADER_FILL = PatternFill("solid", fgColor="17365D")
INFO_FILL = PatternFill("solid", fgColor="D9EAF7")
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
DECISION_FILL = PatternFill("solid", fgColor="E2F0D9")
THIN = Side(style="thin", color="B7C9D6")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry_index() -> dict[str, dict]:
    document = json.loads(KB_PATH.read_text(encoding="utf-8-sig"))
    return {entry["new_entry_id"]: entry for entry in document["ingredients"]}


def condition_index() -> dict[str, str]:
    with SPLIT_PATH.open(encoding="utf-8-sig", newline="") as stream:
        return {row["filename"]: row["category"] for row in csv.DictReader(stream)}


def style_header(sheet, row: int = 1) -> None:
    for cell in sheet[row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


def style_cells(sheet) -> None:
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER


def setup_page(sheet) -> None:
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.page_setup.orientation = "portrait"
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25
    sheet.page_margins.top = 0.35
    sheet.page_margins.bottom = 0.35


def build_case_sheet(workbook: Workbook, case: dict) -> None:
    sheet = workbook.create_sheet(case["id_kasus"])
    sheet.merge_cells("A1:B1")
    sheet["A1"] = f"Validasi Pemetaan Anotasi: {case['id_kasus']}"
    sheet["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    sheet["A1"].fill = HEADER_FILL
    sheet["A1"].alignment = Alignment(horizontal="center")
    rows = [
        ("Nama file", case["nama_file"]),
        ("Kondisi kemasan", case["kondisi_kemasan"]),
        ("Nama ground truth lama", case["nama_gt_lama"]),
        ("Kategori ground truth lama", case["kategori_gt_lama"]),
        ("Span yang dianotasi", case["span_dianotasi"]),
        ("Teks komposisi", case["teks_komposisi"]),
        ("Kandidat A", f"{case['kandidat_A_id']}: {case['kandidat_A_nama']} ({case['kandidat_A_kategori']})"),
        ("Kandidat B", f"{case['kandidat_B_id']}: {case['kandidat_B_nama']} ({case['kandidat_B_kategori']})"),
        ("Petunjuk penilaian", case["petunjuk_penilaian"]),
        ("Keputusan final", "Isi pada sheet keputusan_ahli"),
        ("Catatan ahli", "Isi pada sheet keputusan_ahli"),
    ]
    for index, (label, value) in enumerate(rows, 3):
        sheet.cell(index, 1, label)
        sheet.cell(index, 2, value)
        sheet.cell(index, 1).font = Font(bold=True)
        sheet.cell(index, 1).fill = INFO_FILL
        sheet.cell(index, 1).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(index, 2).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(index, 1).border = BORDER
        sheet.cell(index, 2).border = BORDER
    sheet.row_dimensions[8].height = 190
    sheet.row_dimensions[11].height = 58
    sheet.row_dimensions[12].height = 58
    sheet.column_dimensions["A"].width = 29
    sheet.column_dimensions["B"].width = 95
    setup_page(sheet)
    sheet.print_area = "A1:B13"


def build() -> dict:
    gt = json.loads(GT_PATH.read_text(encoding="utf-8-sig"))
    kb = entry_index()
    conditions = condition_index()
    canonical_names = {entry["standard_name"] for entry in kb.values()}

    absent_counts: dict[str, int] = {}
    for document in gt.values():
        for item in document.get("ingredients", []):
            name = str(item["standard_name"])
            if name not in canonical_names:
                absent_counts[name] = absent_counts.get(name, 0) + 1

    workbook = Workbook()
    instructions = workbook.active
    instructions.title = "petunjuk"
    instructions.merge_cells("A1:B1")
    instructions["A1"] = "Validasi Pemetaan Anotasi Ground Truth ke KB v2"
    instructions["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    instructions["A1"].fill = HEADER_FILL
    instructions["A1"].alignment = Alignment(horizontal="center")
    notes = [
        "Tujuan", "Memastikan tiga anotasi ground truth yang tidak dapat dipetakan otomatis ke nama kanonis knowledge base versi 2.",
        "Cara menilai", "Buka sheet MAP-01 sampai MAP-03. Pilih kandidat berdasarkan teks komposisi tercetak, bukan keluaran OCR atau performa sistem.",
        "Pengisian", "Isi keputusan_final dan catatan_ahli pada sheet keputusan_ahli. Pilih TIDAK_DAPAT_DITETAPKAN bila teks label tidak cukup untuk memilih kandidat.",
        "Batas", "Workbook ini hanya mencatat keputusan pemetaan anotasi. Workbook tidak mengubah ground truth, konfigurasi evaluasi, atau hasil sistem.",
    ]
    for row in range(0, len(notes), 2):
        target = row // 2 + 3
        instructions.cell(target, 1, notes[row])
        instructions.cell(target, 2, notes[row + 1])
        instructions.cell(target, 1).font = Font(bold=True)
        instructions.cell(target, 1).fill = INFO_FILL
        for col in (1, 2):
            instructions.cell(target, col).border = BORDER
            instructions.cell(target, col).alignment = Alignment(vertical="top", wrap_text=True)
    instructions.column_dimensions["A"].width = 20
    instructions.column_dimensions["B"].width = 100
    for row in range(3, 7):
        instructions.row_dimensions[row].height = 40
    setup_page(instructions)
    instructions.print_area = "A1:B6"

    cases = []
    case_number = 1
    for filename, document in sorted(gt.items()):
        for item in document.get("ingredients", []):
            old_name = str(item["standard_name"])
            if old_name not in AMBIGUOUS_CASES:
                continue
            candidate_a, candidate_b, guidance = AMBIGUOUS_CASES[old_name]
            a, b = kb[candidate_a], kb[candidate_b]
            cases.append({
                "id_kasus": f"MAP-{case_number:02d}", "nama_file": filename,
                "kondisi_kemasan": conditions[filename], "teks_komposisi": document["ground_truth_text"],
                "span_dianotasi": item["matched_variant"], "nama_gt_lama": old_name,
                "kategori_gt_lama": item["category"], "kandidat_A_id": candidate_a,
                "kandidat_A_nama": a["standard_name"], "kandidat_A_kategori": a["category"],
                "kandidat_B_id": candidate_b, "kandidat_B_nama": b["standard_name"],
                "kandidat_B_kategori": b["category"], "petunjuk_penilaian": guidance,
            })
            case_number += 1

    decisions = workbook.create_sheet("keputusan_ahli")
    decision_headers = ["id_kasus", "nama_file", "span_dianotasi", "nama_gt_lama", "kandidat_A", "kandidat_B", "keputusan_final", "catatan_ahli"]
    decisions.append(decision_headers)
    for case in cases:
        decisions.append([
            case["id_kasus"], case["nama_file"], case["span_dianotasi"], case["nama_gt_lama"],
            case["kandidat_A_id"], case["kandidat_B_id"], "", "",
        ])
    style_header(decisions)
    decisions.freeze_panes = "A2"
    decisions.auto_filter.ref = decisions.dimensions
    widths = {"A": 13, "B": 22, "C": 20, "D": 35, "E": 18, "F": 18, "G": 30, "H": 55}
    for column, width in widths.items():
        decisions.column_dimensions[column].width = width
    style_cells(decisions)
    for row_number in range(2, decisions.max_row + 1):
        decisions.cell(row_number, 7).fill = DECISION_FILL
        decisions.cell(row_number, 8).fill = DECISION_FILL
        decisions.row_dimensions[row_number].height = 38
    validation = DataValidation(type="list", formula1='"v2-028a,v2-028b,v2-234a,v2-234b,TIDAK_DAPAT_DITETAPKAN"', allow_blank=False)
    validation.errorTitle = "Pilihan keputusan tidak valid"
    validation.error = "Pilih salah satu kandidat KB v2 atau TIDAK_DAPAT_DITETAPKAN."
    validation.promptTitle = "Keputusan pemetaan"
    validation.prompt = "Pilih kandidat yang didukung teks label."
    decisions.add_data_validation(validation)
    validation.add(f"G2:G{decisions.max_row}")
    decisions.conditional_formatting.add(f"G2:G{decisions.max_row}", FormulaRule(formula=["$G2=\"\""], fill=WARNING_FILL))
    setup_page(decisions)
    decisions.page_setup.orientation = "landscape"
    decisions.print_area = f"A1:H{decisions.max_row}"

    for case in cases:
        build_case_sheet(workbook, case)

    direct_sheet = workbook.create_sheet("pemetaan_otomatis")
    direct_headers = ["nama_gt_lama", "jumlah_anotasi", "target_kb_v2_id", "nama_kanonis_kb_v2", "kategori_gt", "kategori_kb_v2", "dasar_pemetaan"]
    direct_sheet.append(direct_headers)
    for mapping in DIRECT_MAPPINGS:
        entry = kb[mapping["target_id"]]
        direct_sheet.append([mapping["nama_gt_lama"], absent_counts.get(mapping["nama_gt_lama"], 0), mapping["target_id"], entry["standard_name"], "aman", entry["category"], mapping["alasan"]])
    style_header(direct_sheet)
    direct_sheet.freeze_panes = "A2"
    direct_sheet.auto_filter.ref = direct_sheet.dimensions
    for column, width in {"A": 55, "B": 18, "C": 18, "D": 55, "E": 15, "F": 15, "G": 60}.items():
        direct_sheet.column_dimensions[column].width = width
    style_cells(direct_sheet)
    setup_page(direct_sheet)
    direct_sheet.page_setup.orientation = "landscape"
    direct_sheet.print_area = f"A1:G{direct_sheet.max_row}"

    provenance = workbook.create_sheet("provenance")
    provenance.append(["item", "nilai"])
    for row in [
        ("tujuan", "Validasi manual untuk tiga anotasi GT yang membutuhkan pemilihan cabang KB v2."),
        ("jumlah_kasus_ambigu", len(cases)),
        ("jumlah_pemetaan_otomatis", sum(absent_counts.get(row["nama_gt_lama"], 0) for row in DIRECT_MAPPINGS)),
        ("ground_truth_path", str(GT_PATH.relative_to(ROOT)).replace("\\", "/")),
        ("ground_truth_sha256", sha256(GT_PATH)),
        ("kb_v2_path", str(KB_PATH.relative_to(ROOT)).replace("\\", "/")),
        ("kb_v2_sha256", sha256(KB_PATH)),
        ("split_path", str(SPLIT_PATH.relative_to(ROOT)).replace("\\", "/")),
        ("split_sha256", sha256(SPLIT_PATH)),
    ]:
        provenance.append(row)
    style_header(provenance)
    provenance.column_dimensions["A"].width = 30
    provenance.column_dimensions["B"].width = 110
    style_cells(provenance)
    setup_page(provenance)
    provenance.print_area = f"A1:B{provenance.max_row}"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    workbook.properties.creator = "LensaLabel"
    workbook.save(OUT_PATH)
    workbook.close()
    return {"output": str(OUT_PATH), "ambiguous_cases": len(cases), "direct_annotations": sum(absent_counts.get(row["nama_gt_lama"], 0) for row in DIRECT_MAPPINGS), "ground_truth_sha256": sha256(GT_PATH), "kb_v2_sha256": sha256(KB_PATH)}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
