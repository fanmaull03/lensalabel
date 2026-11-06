"""Apply approved Phase 2 decisions to a separate review-only KB draft."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from build_kb_v2_draft import ROOT, SOURCE, OUT as PHASE1_OUT, unique, workbook


OUT = ROOT / "evaluation/results/kb_v2_phase2"


def build() -> dict:
    original_json = PHASE1_OUT / "kb_v2_draft.json"
    original_mapping = PHASE1_OUT / "old_to_new_mapping.json"
    before_json = original_json.read_bytes()
    before_mapping = original_mapping.read_bytes()
    payload = copy.deepcopy(json.loads(before_json))
    mapping = copy.deepcopy(json.loads(before_mapping))
    entries = payload["ingredients"]
    by_id = {item["new_entry_id"]: item for item in entries}
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    source_by_no = {item["number"]: item for item in source["ingredients"]}

    first, second = by_id["v2-206"], by_id["v2-213"]
    if first["category"] != second["category"]:
        raise ValueError("No. 206/213 berbeda kategori; penggabungan tidak boleh dilanjutkan")
    first["standard_name"] = "Natrium karboksimetil selulosa / Metil selulosa"
    first["synonyms"] = unique([
        *first["synonyms"], second["standard_name"], *second["synonyms"],
        *[variant for no in (206, 213) for variant in source_by_no[no]["synonyms"]],
    ])
    first["synonyms"] = [v for v in first["synonyms"] if v.casefold() != first["standard_name"].casefold()]
    first["additive_codes"] = "INS 461 / INS 465 / INS 466"
    first["old_numbers"] = [206, 213]
    first["old_entry_ids"] = unique([str(x) for x in [*first["old_entry_ids"], *second["old_entry_ids"]]])
    first["old_entry_ids"] = [int(x) for x in first["old_entry_ids"]]
    first["reference_codes"] = unique([*first["reference_codes"], *second["reference_codes"]])
    first["alasan_klinis_catatan_ahli"] = [*first["alasan_klinis_catatan_ahli"],
                                          *second["alasan_klinis_catatan_ahli"]]
    first["status"] = "draf"
    first["code_status"] = "disetujui_pengguna_fase2_kategori_sama"
    first.pop("legacy_additive_codes_unresolved", None)
    entries.remove(second)
    for row in mapping:
        if row["old_no"] in (206, 213):
            row["new_entry_id"] = "v2-206"
            row["jenis_perubahan"] = "merged"
            row["kategori_baru"] = first["category"]

    for entry_id in ("v2-234a", "v2-234b"):
        entry = by_id[entry_id]
        entry["category"] = "perhatian"
        entry["sumber_kategori"] = "turunan_baris_234_ahli"
        entry["status"] = "draf"
        entry.pop("kategori_baris_ahli_sebelum_split", None)
    for row in mapping:
        if row["old_no"] == 234:
            row["kategori_baru"] = "perhatian"

    no11 = source_by_no[11]
    source_variants = unique([no11["standard_name"], *no11["synonyms"]])
    related = [v for v in source_variants if any(w in v.casefold() for w in ("kaldu", "broth", "stock"))]
    neutral = [v for v in related if not any(w in v.casefold() for w in ("terigu", "wheat flour"))]
    if neutral:
        by_id["v2-001"]["synonyms"] = [v for v in by_id["v2-001"]["synonyms"] if v not in neutral]
        by_id["v2-042"]["synonyms"] = unique([*by_id["v2-042"]["synonyms"], *neutral])
    transfer_log = {
        "source_old_no": 11, "target_old_no": 42,
        "variants_containing_kaldu_or_broth": related,
        "variants_moved": neutral,
        "reason": "Semua varian No. 11 yang menyebut kaldu/broth juga menyebut tepung terigu/wheat flour secara eksplisit; tidak ada varian kaldu tanpa rincian yang dapat dipindah." if not neutral else
                  "Hanya varian tanpa penyebutan tepung terigu eksplisit dipindah.",
    }

    for item in entries:
        item["synonyms"] = unique(item["synonyms"])
    code_collisions = {}
    for code in ("E340", "INS 340", "INS340"):
        code_collisions[code] = [item["new_entry_id"] for item in entries
                                 if code.casefold() in {v.casefold() for v in item["synonyms"]}]
    if any(len(ids) != 2 for ids in code_collisions.values()):
        raise ValueError("Jumlah entri duplikat INS 340 berubah dari inventaris v1")

    for proposal in payload["merge_proposals"]:
        if proposal["old_numbers"] == [206, 213]:
            proposal["status"] = "diterapkan_di_draf_fase2"
            proposal["proposed_new_name"] = first["standard_name"]
            proposal["reason"] = "Kategori kedua entri aman; kode 461, 465, 466 dipertahankan sesuai keputusan pengguna."
    for change in payload["code_changes"]:
        if change["old_no"] == 213:
            change["draft_code"] = first["additive_codes"]
            change["status"] = "digabung_dengan_no_206_sesuai_keputusan_pengguna"

    payload["menunggu_keputusan"] = [item for item in payload["menunggu_keputusan"]
                                      if item["item"] == "No. 173 dan No. 200"]
    payload["limitations_and_future_work"] = [
        {"item": "Pernyataan alergen BPOM", "status": "limitasi_dan_future_work",
         "reason": "Tidak dimasukkan ke KB dan tidak dibangun pada Fase 2; closing marker saat ini dapat memotong bagian alergen."},
    ]
    payload["excluded_out_of_scope"] = ["Rujukan", "Format instrumen"]
    payload["phase2_decisions"] = {
        "merged_206_213": first["new_entry_id"],
        "codes_206_213": first["additive_codes"],
        "licorice_categories": {key: by_id[key]["category"] for key in ("v2-234a", "v2-234b")},
        "no11_to_no42": transfer_log,
        "cross_entry_ins340_unchanged": code_collisions,
    }
    payload["version"] = "v2_phase2_review_only"
    payload["phase1_source_sha256"] = {
        "kb_v2_draft.json": hashlib.sha256(before_json).hexdigest(),
        "old_to_new_mapping.json": hashlib.sha256(before_mapping).hexdigest(),
    }

    category_counts = Counter(x["category"] for x in entries)
    summary = {
        "status": "DRAF_FASE2_FILE_SAJA_BELUM_UNTUK_DB_ATAU_GT",
        "entries": len(entries), "variants": sum(1 + len(x["synonyms"]) for x in entries),
        "categories": dict(category_counts),
        "mapping_rows": len(mapping), "old_numbers_mapped": len({x["old_no"] for x in mapping if x["old_no"]}),
        "notes_preserved": sum(bool(x["clinical_note"]) for x in payload["expert_validation_rows"]),
        "no11_variants_moved_to_42": len(neutral),
        "pending_decision_items": len(payload["menunggu_keputusan"]),
    }
    payload["summary"] = summary
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kb_v2_review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "old_to_new_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "phase2_decisions.json").write_text(json.dumps(payload["phase2_decisions"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    kb_headers = ["new_entry_id", "old_numbers", "standard_name", "category", "sumber_kategori", "additive_codes",
                  "english_synonyms", "synonyms", "varian_pendek_baru_1_2_kata",
                  "alasan_klinis_catatan_ahli", "status", "reference_codes"]
    workbook(OUT / "kb_v2_review.xlsx", {
        "kb_v2": (kb_headers, [[item.get(key) for key in kb_headers] for item in entries]),
        "validasi_ahli_240": (list(payload["expert_validation_rows"][0]),
                                [list(row.values()) for row in payload["expert_validation_rows"]]),
        "kode_ins": (list(payload["code_changes"][0]), [list(row.values()) for row in payload["code_changes"]]),
        "gabungan_usulan": (list(payload["merge_proposals"][0]), [list(row.values()) for row in payload["merge_proposals"]]),
        "bahan_baru_ahli": (list(payload["presence_note3"][0]), [list(row.values()) for row in payload["presence_note3"]]),
        "turunan_definisi": (list(payload["derived_longest_match"][0]), [list(row.values()) for row in payload["derived_longest_match"]]),
        "varian_pendek": (list(payload["short_new_variants_for_review"][0]),
                           [list(row.values()) for row in payload["short_new_variants_for_review"]]),
        "ins340_lintas_entri": (["kode", "new_entry_ids"], [[code, ids] for code, ids in code_collisions.items()]),
        "menunggu_keputusan": (list(payload["menunggu_keputusan"][0]),
                                [list(row.values()) for row in payload["menunggu_keputusan"]]),
    })
    map_headers = ["old_no", "old_entry_id", "new_entry_id", "jenis_perubahan", "kategori_lama", "kategori_baru"]
    workbook(OUT / "old_to_new_mapping.xlsx", {
        "mapping": (map_headers, [[row[key] for key in map_headers] for row in mapping]),
    })
    (OUT / "phase2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
