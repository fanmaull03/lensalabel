"""Build a review-only KB v2 draft from the signed dietitian worksheet."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "backend/app/db/knowledge_base_gfcf.json"
SNAPSHOT = ROOT / "evaluation/kb_snapshot.json"
ARCHIVE = ROOT / "archive/kb_v1_and_gt_before_expert"
OUT = ROOT / "evaluation/results/kb_v2_draft"
CATEGORIES = {"Aman": "aman", "Perlu Perhatian": "perhatian", "Hindari": "hindari"}
VALIDATOR = "Ahli Gizi 1"
VALIDATED_AT = "2026-10-05"

# Every proposed label below is either in the dietitian's note 3 or a direct
# Indonesian/English rendering of the same ingredient, not an extra substance.
NOTE3 = [
    ("gluten/vital wheat gluten", "Gluten / vital wheat gluten", ["Gluten", "Vital wheat gluten"], "hindari", [], [1]),
    ("seitan", "Seitan", [], "hindari", [], []),
    ("spelt", "Spelt", [], "hindari", [], []),
    ("kamut", "Kamut", [], "hindari", [], []),
    ("triticale", "Triticale", [], "hindari", [], []),
    ("dedak dan lembaga gandum (wheat bran/germ)", "Dedak dan lembaga gandum", ["Dedak gandum", "Lembaga gandum", "Wheat bran", "Wheat germ"], "hindari", [], [1]),
    ("tepung gandum utuh", "Tepung gandum utuh", ["Whole wheat flour"], "hindari", [1], [1]),
    ("protein gandum terhidrolisis", "Protein gandum terhidrolisis", ["Hydrolyzed wheat protein"], "hindari", [], [31, 32]),
    ("susu kambing/kerbau", "Susu kambing / susu kerbau", ["Susu kambing", "Susu kerbau", "Goat milk", "Buffalo milk"], "hindari", [], [15]),
    ("susu bebas laktosa", "Susu bebas laktosa", ["Lactose-free milk"], "hindari", [], [15]),
    ("ghee/butter oil", "Ghee / butter oil", ["Ghee", "Butter oil"], "hindari", [19], [19]),
    ("buttermilk", "Buttermilk", [], "hindari", [], [19]),
    ("keju bubuk", "Keju bubuk", ["Cheese powder"], "hindari", [17], [17]),
    ("whey permeate/permeat susu", "Whey permeate / permeat susu", ["Whey permeate", "Permeat susu"], "hindari", [], [21]),
    ("konsentrat protein susu (MPC)", "Konsentrat protein susu (MPC)", ["Konsentrat protein susu", "Milk protein concentrate", "MPC"], "hindari", [], [15]),
    ("laktoferin", "Laktoferin", ["Lactoferrin"], "hindari", [], []),
    ("beta-laktoglobulin", "Beta-laktoglobulin", ["Beta-lactoglobulin"], "hindari", [], []),
    ("kasein terhidrolisis", "Kasein terhidrolisis", ["Hydrolyzed casein"], "hindari", [22], [22]),
    ("es krim", "Es krim", ["Ice cream"], "hindari", [], [20]),
    ("cokelat susu", "Cokelat susu", ["Milk chocolate"], "hindari", [], [15, 97]),
    ("perisa keju/susu/mentega", "Perisa keju / susu / mentega", ["Perisa keju", "Perisa susu", "Perisa mentega", "Cheese flavor", "Milk flavor", "Butter flavor"], "perhatian", [], [41]),
    ("mi soba", "Mi soba", ["Soba noodles"], "perhatian", [], [113]),
    ("kecap manis tanpa rincian", "Kecap manis tanpa rincian", ["Sweet soy sauce without ingredient details"], "perhatian", [], [12]),
]

DERIVED = [
    ("susu kedelai", "Susu kedelai", [], "aman", "existing", [145]),
    ("susu kelapa", "Susu kelapa", [], "aman", "existing", [142]),
    ("susu beras", "Susu beras", [], "aman", "existing", [143]),
    ("susu almond", "Susu almond", [], "aman", "existing", [144]),
    ("cocoa butter", "Cocoa butter", ["Lemak kakao"], "aman", "new", []),
    ("peanut butter", "Peanut butter", ["Selai kacang tanah"], "aman", "new", []),
    ("krimer nabati", "Krimer nabati", ["Plant-based creamer"], "perhatian", "alias", [29]),
    ("cream of tartar", "Cream of tartar", ["Krim tartar"], "aman", "new", []),
]

NOTE3_ENGLISH = {
    "gluten/vital wheat gluten": "Gluten / Vital wheat gluten",
    "seitan": "Seitan", "spelt": "Spelt", "kamut": "Kamut", "triticale": "Triticale",
    "dedak dan lembaga gandum (wheat bran/germ)": "Wheat bran / Wheat germ",
    "tepung gandum utuh": "Whole wheat flour",
    "protein gandum terhidrolisis": "Hydrolyzed wheat protein",
    "susu kambing/kerbau": "Goat milk / Buffalo milk",
    "susu bebas laktosa": "Lactose-free milk",
    "ghee/butter oil": "Ghee / Butter oil",
    "buttermilk": "Buttermilk", "keju bubuk": "Cheese powder",
    "whey permeate/permeat susu": "Whey permeate",
    "konsentrat protein susu (MPC)": "Milk protein concentrate",
    "laktoferin": "Lactoferrin", "beta-laktoglobulin": "Beta-lactoglobulin",
    "kasein terhidrolisis": "Hydrolyzed casein", "es krim": "Ice cream",
    "cokelat susu": "Milk chocolate",
    "perisa keju/susu/mentega": "Cheese flavor / Milk flavor / Butter flavor",
    "mi soba": "Soba noodles",
    "kecap manis tanpa rincian": "Sweet soy sauce without ingredient details",
}


def unique(values: list[str]) -> list[str]:
    seen, result = set(), []
    for value in values:
        value = value.strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def no_contacts(value: str) -> bool:
    patterns = (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                r"\b(?:\+?62|0)8\d[\d\s-]{7,}\b",
                r"\b(?:STR|NIDN|NIP)\s*[:#-]?\s*\d{5,}\b")
    return not any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def workbook(path: Path, sheets: dict[str, tuple[list[str], list[list]]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for title, (headers, rows) in sheets.items():
        ws = wb.create_sheet(title)
        ws.append(headers)
        for row in rows:
            ws.append([json.dumps(cell, ensure_ascii=False) if isinstance(cell, (dict, list)) else cell for cell in row])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24435B")
        for col in ws.columns:
            letter = col[0].column_letter
            width = min(78, max(12, max(len(str(c.value or "")) for c in col[:min(len(col), 100)]) + 2))
            ws.column_dimensions[letter].width = width
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    wb.save(path)


def build(docx_path: Path, out: Path) -> dict:
    source_bytes = SOURCE.read_bytes()
    snapshot_bytes = SNAPSHOT.read_bytes()
    for name, data in ((SOURCE.name, source_bytes), (SNAPSHOT.name, snapshot_bytes)):
        if (ARCHIVE / name).read_bytes() != data:
            raise ValueError(f"Arsip v1 tidak identik: {name}")
    source = json.loads(source_bytes)
    old = {row["number"]: row for row in source["ingredients"]}
    snapshot = json.loads(snapshot_bytes)
    ids = {row["standard_name"]: row["ingredient_id"] for row in snapshot}
    if len(old) != 240 or len(ids) != 240:
        raise ValueError("KB v1 bukan 240 entri")
    doc = Document(docx_path)
    table = doc.tables[1]
    if len(table.rows) != 241 or len(table.columns) != 8:
        raise ValueError("Tabel ahli bukan 240 x 8")
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows[1:]]
    if [int(row[0]) for row in rows] != list(range(1, 241)):
        raise ValueError("Nomor tabel ahli tidak lengkap")
    if any(old[int(row[0])]["standard_name"].casefold() != row[1].casefold() for row in rows):
        raise ValueError("Nama bahan di tabel ahli berbeda dari KB v1")
    if any(not no_contacts(row[7]) for row in rows):
        raise ValueError("Catatan tabel mengandung kemungkinan identitas kontak")
    if Counter(row[4] for row in rows) != {"Aman": 118, "Perlu Perhatian": 80, "Hindari": 42}:
        raise ValueError("Distribusi kategori awal tidak cocok")
    if sum(bool(row[7]) for row in rows) != 71:
        raise ValueError("Jumlah catatan ahli tidak cocok")

    expert = {}
    validations = []
    for row in rows:
        n = int(row[0])
        final = row[4] if row[6] == "Setuju" else row[6]
        if final not in CATEGORIES:
            raise ValueError(f"Kategori ahli No. {n} tidak dikenal")
        expert[n] = {"category": CATEGORIES[final], "initial": CATEGORIES[row[4]],
                     "correction": row[6], "note": row[7]}
        validations.append({"old_no": n, "old_entry_id": ids[old[n]["standard_name"]],
                            "category_initial": CATEGORIES[row[4]], "expert_correction": row[6],
                            "category_expert": CATEGORIES[final], "clinical_note": row[7],
                            "validator": VALIDATOR, "validated_at": VALIDATED_AT})
    if Counter(x["category_expert"] for x in validations) != {"aman": 153, "perhatian": 55, "hindari": 32}:
        raise ValueError("Distribusi kategori ahli tidak cocok")
    if sum(x["category_initial"] != x["category_expert"] for x in validations) != 69:
        raise ValueError("Jumlah koreksi kategori tidak cocok")

    entries: dict[str, dict] = {}
    by_old: dict[int, list[str]] = {}
    def make_entry(numbers: list[int], entry_id: str, *, name: str | None = None,
                   category: str | None = None, synonyms: list[str] | None = None,
                   status: str = "draf") -> dict:
        first = old[numbers[0]]
        record = {"new_entry_id": entry_id, "old_numbers": numbers,
                  "old_entry_ids": [ids[old[n]["standard_name"]] for n in numbers],
                  "standard_name": name or first["standard_name"],
                  "english_synonyms": " / ".join(unique([old[n]["english_synonyms"] for n in numbers])),
                  "additive_codes": " / ".join(unique([old[n]["additive_codes"] for n in numbers if old[n]["additive_codes"] != "-"])) or "-",
                  "category": category if category is not None else expert[numbers[0]]["category"],
                  "sumber_kategori": "isian_langsung_ahli" if status != "menunggu_keputusan" else "menunggu_keputusan",
                  "synonyms": unique(synonyms if synonyms is not None else
                                     [variant for n in numbers for variant in [old[n]["standard_name"], *old[n]["synonyms"]]]),
                  "reference_codes": unique([ref for n in numbers for ref in old[n]["reference_codes"]]),
                  "alasan_klinis_catatan_ahli": [{"old_no": n, "text": expert[n]["note"]} for n in numbers if expert[n]["note"]],
                  "status": status}
        record["synonyms"] = [x for x in record["synonyms"] if x.casefold() != record["standard_name"].casefold()]
        entries[entry_id] = record
        for n in numbers:
            by_old.setdefault(n, []).append(entry_id)
        return record

    merged_groups = [[1, 11], [31, 32], [147, 178, 179]]
    grouped = {n for group in merged_groups for n in group}
    for n in range(1, 241):
        if n in grouped or n in (28, 234):
            continue
        make_entry([n], f"v2-{n:03d}")
    sugar_name = "Gula pasir murni / Sukrosa / Gula merah dan varian gula"
    for group in merged_groups:
        if len({expert[n]["category"] for n in group}) != 1:
            raise ValueError(f"Kategori gabungan berbeda: {group}")
        make_entry(group, f"v2-{group[0]:03d}", name=sugar_name if group[0] == 147 else None)

    # Explicit expert split. Unqualified margarine belongs to the attention entry.
    make_entry([28], "v2-028a", name="Margarin mengandung susu/whey", category="hindari",
               synonyms=["Margarine containing whey/milk solids", "Margarin mengandung susu", "Margarin mengandung whey"])
    make_entry([28], "v2-028b", name="Margarin (komposisi tidak dirinci)", category="perhatian",
               synonyms=["Margarin", "Margarine"])

    # The expert changed the unsplit licorice category but did not assign
    # separate categories to extract and candy. Both remain review-only.
    for suffix, name, variants in (("a", "Ekstrak licorice", ["Licorice extract"]),
                                   ("b", "Permen licorice", ["Licorice candy"])):
        item = make_entry([234], f"v2-234{suffix}", name=name, synonyms=variants,
                          status="menunggu_keputusan")
        item["category"] = None
        item["sumber_kategori"] = "menunggu_keputusan"
        item["kategori_baris_ahli_sebelum_split"] = expert[234]["category"]

    def remove_codes(item: dict, codes: list[str]) -> None:
        targets = {normalized(value) for value in codes}
        item["synonyms"] = [x for x in item["synonyms"] if normalized(x) not in targets]
        item["additive_codes"] = "-"

    code_changes = []
    for n, forbidden in {22: ["E469", "INS 469", "INS469"],
                         29: ["E469", "INS 469", "INS469", "E470", "INS 470", "INS470"],
                         36: ["E1400", "INS 1400", "INS1400"],
                         70: ["E965", "INS 965", "INS965"],
                         209: ["E314i", "INS 314i", "INS314i", "E314", "INS 314", "INS314"]}.items():
        item = entries[f"v2-{n:03d}"]
        before = item["additive_codes"]
        remove_codes(item, forbidden)
        code_changes.append({"old_no": n, "old_code": before, "draft_code": "-", "status": "diterapkan_di_draf"})
    for n, replacement in ((69, "INS 924a"), (171, "INS 500(ii)")):
        item = entries[f"v2-{n:03d}"]
        before = item["additive_codes"]
        if n == 171:
            item["synonyms"] = [x for x in item["synonyms"] if normalized(x) not in
                                {normalized(v) for v in ["E500(i)", "INS 500(i)", "INS500(i)"]}]
        item["additive_codes"] = replacement
        item["synonyms"] = unique([*item["synonyms"], replacement, replacement.replace(" ", "")])
        code_changes.append({"old_no": n, "old_code": before, "draft_code": replacement,
                             "status": "diterapkan_di_draf"})

    folate = entries["v2-072"]
    folate["standard_name"] = "Asam folat"
    folate["synonyms"] = unique([x for x in folate["synonyms"] if "fortif" not in x.casefold()] + ["Folic acid"])
    folate["synonyms"] = [x for x in folate["synonyms"] if x.casefold() != "asam folat"]

    # No. 206 already owns INS 466. Do not assign a code to the combined
    # methylcellulose/CMC entry until the component-level mapping is approved.
    cellulose = entries["v2-213"]
    cellulose["legacy_additive_codes_unresolved"] = cellulose["additive_codes"]
    remove_codes(cellulose, ["E461", "INS 461", "INS461", "E465", "INS 465", "INS465"])
    cellulose["code_status"] = "menunggu_keputusan_pemisahan_per_bahan"
    cellulose["status"] = "menunggu_keputusan_kode"
    code_changes.append({"old_no": 213, "old_code": "INS 461/465", "draft_code": "-",
                         "status": "kode_ditahan_menunggu_pemisahan"})

    presence = []
    new_counter = 0
    for label, name, variants, category, alias_targets, overlaps in NOTE3:
        exact = [row for row in snapshot if normalized(row["name_variant"]) == normalized(name)
                 or any(normalized(row["name_variant"]) == normalized(v) for v in variants)]
        if exact:
            exact_ids = {x["ingredient_id"] for x in exact}
            if len(exact_ids) != 1:
                raise ValueError(f"Entri lama ambigu untuk bahan ahli: {label}")
            old_no = next(n for n, item in old.items() if ids[item["standard_name"]] in exact_ids)
            target = entries[by_old[old_no][0]]
            if target["category"] != category:
                raise ValueError(f"Kategori varian lama bertabrakan: {label}")
            target["synonyms"] = unique([*target["synonyms"], name, *variants])
            target["synonyms"] = [x for x in target["synonyms"] if x.casefold() != target["standard_name"].casefold()]
            presence.append({"bahan_ahli": label, "kategori_ahli": category,
                             "status": "sudah_ada", "existing_entry_ids": sorted(exact_ids),
                             "existing_names": unique([x["standard_name"] for x in exact]),
                             "tindakan": "varian_bahasa_indonesia_dilengkapi_tanpa_duplikasi",
                             "new_entry_id": target["new_entry_id"]})
            continue
        related = [old[n]["standard_name"] for n in overlaps]
        if alias_targets:
            target = entries[by_old[alias_targets[0]][0]]
            if target["category"] != category:
                raise ValueError(f"Kategori varian bertabrakan: {label}")
            target["synonyms"] = unique([*target["synonyms"], name, *variants])
            status, action, new_id = "tumpang_tindih", "varian_entri_ada_tanpa_duplikasi", target["new_entry_id"]
        else:
            new_counter += 1
            new_id = f"v2-new-{new_counter:03d}"
            entries[new_id] = {"new_entry_id": new_id, "old_numbers": [], "old_entry_ids": [],
                               "standard_name": name, "english_synonyms": NOTE3_ENGLISH[label],
                               "additive_codes": "-", "category": category,
                               "sumber_kategori": "isian_langsung_ahli",
                               "synonyms": [v for v in unique(variants) if v.casefold() != name.casefold()],
                               "reference_codes": [], "alasan_klinis_catatan_ahli": [],
                               "source_note": "catatan tambahan ahli no. 3", "status": "draf"}
            status, action = ("tumpang_tindih" if overlaps else "baru"), "entri_baru_spesifik"
        presence.append({"bahan_ahli": label, "kategori_ahli": category, "status": status,
                         "existing_entry_ids": [ids[x] for x in related], "existing_names": related,
                         "tindakan": action, "new_entry_id": new_id})

    derived = []
    for label, name, variants, category, status, numbers in DERIVED:
        exact = [x for x in snapshot if normalized(x["name_variant"]) == normalized(name)]
        if status == "existing":
            if not exact:
                raise ValueError(f"Entri turunan yang seharusnya ada hilang: {label}")
            old_ids = sorted({x["ingredient_id"] for x in exact})
            if len(old_ids) != 1:
                raise ValueError(f"Alias ambigu: {label}")
            old_no = next(n for n, item in old.items() if ids[item["standard_name"]] == old_ids[0])
            target = entries[by_old[old_no][0]]
            action, new_id = "sudah_ada_tidak_diduplikasi", target["new_entry_id"]
            category_v1 = old[old_no]["category"]
        elif status == "alias":
            target = entries[by_old[numbers[0]][0]]
            if target["category"] != category:
                raise ValueError(f"Kategori krimer tidak konsisten: {label}")
            target["synonyms"] = unique([*target["synonyms"], name, *variants])
            action, new_id = "varian_no_29_tanpa_entri_baru", target["new_entry_id"]
            category_v1 = old[numbers[0]]["category"]
        else:
            if exact:
                raise ValueError(f"Duplikasi entri turunan: {label}")
            new_counter += 1
            new_id = f"v2-new-{new_counter:03d}"
            entries[new_id] = {"new_entry_id": new_id, "old_numbers": [], "old_entry_ids": [],
                               "standard_name": name, "english_synonyms": name,
                               "additive_codes": "-", "category": category,
                               "sumber_kategori": "diturunkan_dari_definisi_ahli",
                               "synonyms": variants, "reference_codes": [],
                               "alasan_klinis_catatan_ahli": [], "source_note": "catatan tambahan ahli no. 1 dan 5",
                               "status": "draf"}
            action = "entri_baru_turunan_definisi"
            category_v1 = None
        derived.append({"bahan": label, "status": status, "kategori_v1":
                        category_v1,
                        "kategori_draf": category, "sumber_kategori": "diturunkan_dari_definisi_ahli",
                        "tindakan": action, "new_entry_id": new_id})

    merge_proposals = []
    for group in [*merged_groups, [206, 213]]:
        done = group != [206, 213]
        name = (entries[by_old[group[0]][0]]["standard_name"] if done else
                "Natrium karboksimetil selulosa / Metil selulosa")
        merge_proposals.append({"old_numbers": group,
                                "old_entry_ids": [ids[old[n]["standard_name"]] for n in group],
                                "old_names": [old[n]["standard_name"] for n in group],
                                "categories_v1": [old[n]["category"] for n in group],
                                "categories_expert": [expert[n]["category"] for n in group],
                                "proposed_new_name": name,
                                "proposed_category": expert[group[0]]["category"],
                                "proposed_variants": unique([v for n in group for v in
                                                             [old[n]["standard_name"], *old[n]["synonyms"]]]),
                                "status": "diterapkan_di_draf" if done else "menunggu_keputusan_kode_per_bahan",
                                "reason": "INS 461/465 pada entri campuran; CMC 466 sudah pada No. 206" if not done else "sinonim sesuai catatan ahli no. 4"})

    pending = [
        {"item": "No. 206 + 213", "jenis": "kode_dan_penggabungan",
         "alasan": "CMC = INS 466; No. 213 mencampur metil selulosa/CMC dan kode INS 461/465. Perlu penetapan kode per bahan sebelum penggabungan final.",
         "usulan_untuk_ditinjau": "CMC tetap berkode INS 466 di No. 206; pisahkan kode metil selulosa dari CMC. Kode No. 213 ditahan di draf."},
        {"item": "No. 234", "jenis": "kategori_hasil_split",
         "alasan": "Ahli memberi Perlu Perhatian pada Licorice gabungan, belum menetapkan kategori terpisah untuk ekstrak dan permen.",
         "usulan_untuk_ditinjau": "Tetapkan kategori Ekstrak licorice dan Permen licorice masing-masing."},
        {"item": "Pernyataan alergen BPOM", "jenis": "desain_pipeline",
         "alasan": "Marker ALLERGEN yang berlaku sekarang dapat memotong pernyataan sesudah komposisi.",
         "usulan_untuk_ditinjau": "Tentukan desain penanganan pernyataan alergen; belum dimasukkan ke KB."},
        {"item": "No. 11 dan No. 42", "jenis": "kaldu_tanpa_rincian",
         "alasan": "Ahli menyebut kaldu tanpa rincian dapat digabung No. 42, tanpa instruksi varian spesifik.",
         "usulan_untuk_ditinjau": "Tentukan apakah perlu pemetaan varian setelah pemeriksaan ahli."},
        {"item": "Rujukan dan format instrumen", "jenis": "di_luar_data_bahan",
         "alasan": "Catatan ahli no. 6 dan 7 menyarankan tambahan rujukan serta pemisahan kolom alasan klinis/catatan konsumsi.",
         "usulan_untuk_ditinjau": "Tangani dalam instrumen/metode terpisah; tidak mengubah isi KB draf."},
        {"item": "No. 173 dan No. 200", "jenis": "duplikasi_kode_warisan_v1",
         "alasan": "Alias E340, INS 340, dan INS340 sudah terpasang pada dua entri v1 yang berbeda; ahli tidak memberi koreksi untuk pasangan ini.",
         "usulan_untuk_ditinjau": "Konfirmasi pengaitan kode dengan ahli sebelum mengaktifkan KB v2; tidak diubah pada draf."},
    ]

    mapping = []
    merged_numbers = grouped
    code_numbers = {x["old_no"] for x in code_changes}
    for n in range(1, 241):
        for new_id in by_old[n]:
            item = entries[new_id]
            if n in merged_numbers:
                change = "merged"
            elif n in (28, 234):
                change = "split"
            elif n == 72:
                change = "renamed"
            elif n in code_numbers:
                change = "code_changed"
            elif expert[n]["category"] != old[n]["category"]:
                change = "category_changed"
            else:
                change = "unchanged"
            mapping.append({"old_no": n, "old_entry_id": ids[old[n]["standard_name"]],
                            "new_entry_id": new_id, "jenis_perubahan": change,
                            "kategori_lama": old[n]["category"], "kategori_baru": item["category"]})
    for item in entries.values():
        if not item["old_numbers"]:
            mapping.append({"old_no": None, "old_entry_id": None,
                            "new_entry_id": item["new_entry_id"], "jenis_perubahan": "new",
                            "kategori_lama": None, "kategori_baru": item["category"]})

    items = list(entries.values())
    old_variant_norms = {normalized(row["name_variant"]) for row in snapshot}
    short_variant_rows = []
    for item in items:
        item["varian_pendek_baru_1_2_kata"] = []
        for variant in [item["standard_name"], *item["synonyms"]]:
            if normalized(variant) in old_variant_norms:
                continue
            count = len(re.findall(r"\w+", variant))
            if count <= 2:
                item["varian_pendek_baru_1_2_kata"].append(variant)
                short_variant_rows.append({"new_entry_id": item["new_entry_id"],
                                           "standard_name": item["standard_name"],
                                           "variant": variant, "jumlah_kata": count,
                                           "sumber_kategori": item["sumber_kategori"]})
    if len({x["new_entry_id"] for x in items}) != len(items):
        raise ValueError("ID draf duplikat")
    if any(not no_contacts(note["text"]) for item in items for note in item["alasan_klinis_catatan_ahli"]):
        raise ValueError("Data kontak terdeteksi pada keluaran")
    by_category = Counter(item["category"] or "menunggu_keputusan" for item in items)
    variant_total = sum(1 + len(item["synonyms"]) for item in items)
    summary = {"status": "DRAF_FILE_SAJA_BELUM_UNTUK_DB_ATAU_MATCHER",
               "source_sha256": {str(SOURCE.relative_to(ROOT)): hashlib.sha256(source_bytes).hexdigest(),
                                 str(SNAPSHOT.relative_to(ROOT)): hashlib.sha256(snapshot_bytes).hexdigest(),
                                 "docx": hashlib.sha256(docx_path.read_bytes()).hexdigest()},
               "v1_entries": 240, "v1_variants": len(snapshot),
               "expert_categories_before_structural_edits": dict(Counter(v["category_expert"] for v in validations)),
               "v2_entries_including_pending": len(items), "v2_variant_total_including_pending": variant_total,
               "v2_categories": dict(by_category),
               "v2_entries_with_category": sum(x["category"] is not None for x in items),
               "v2_variants_on_categorized_entries": sum(1+len(x["synonyms"]) for x in items if x["category"] is not None),
               "expert_note_rows_preserved": sum(bool(x["clinical_note"]) for x in validations),
               "note3_entries_new": sum(x["tindakan"] == "entri_baru_spesifik" for x in presence),
               "note3_aliases_existing": sum(x["tindakan"] == "varian_entri_ada_tanpa_duplikasi" for x in presence),
               "derived_entries_new": sum(x["tindakan"] == "entri_baru_turunan_definisi" for x in derived),
               "short_new_variants_for_review": len(short_variant_rows),
               "pending_decision_items": len(pending)}
    out.mkdir(parents=True, exist_ok=True)
    payload = {"version": "v2_draft_after_expert_validation", "validator": VALIDATOR,
               "validated_at": VALIDATED_AT, "source_document": docx_path.name,
               "summary": summary, "ingredients": items, "expert_validation_rows": validations,
               "code_changes": code_changes, "merge_proposals": merge_proposals,
               "presence_note3": presence, "derived_longest_match": derived,
               "short_new_variants_for_review": short_variant_rows,
               "menunggu_keputusan": pending}
    (out / "kb_v2_draft.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "old_to_new_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kb_headers = ["new_entry_id", "old_numbers", "standard_name", "category", "sumber_kategori", "additive_codes",
                  "english_synonyms", "synonyms", "varian_pendek_baru_1_2_kata",
                  "alasan_klinis_catatan_ahli", "status", "reference_codes"]
    workbook(out / "kb_v2_draft.xlsx", {
        "kb_v2": (kb_headers, [[item.get(key) for key in kb_headers] for item in items]),
        "validasi_ahli_240": (list(validations[0]), [list(row.values()) for row in validations]),
        "kode_ins": (list(code_changes[0]), [list(row.values()) for row in code_changes]),
        "gabungan_usulan": (list(merge_proposals[0]), [list(row.values()) for row in merge_proposals]),
        "bahan_baru_ahli": (list(presence[0]), [list(row.values()) for row in presence]),
        "turunan_definisi": (list(derived[0]), [list(row.values()) for row in derived]),
        "varian_pendek": (list(short_variant_rows[0]), [list(row.values()) for row in short_variant_rows]),
        "menunggu_keputusan": (list(pending[0]), [list(row.values()) for row in pending]),
    })
    map_headers = ["old_no", "old_entry_id", "new_entry_id", "jenis_perubahan", "kategori_lama", "kategori_baru"]
    workbook(out / "old_to_new_mapping.xlsx", {"mapping": (map_headers, [[row[key] for key in map_headers] for row in mapping])})
    (out / "phase1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(build(args.docx, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
