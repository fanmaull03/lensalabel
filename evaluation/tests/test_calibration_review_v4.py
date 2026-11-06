"""V4 memisahkan deteksi otomatis, persetujuan manual, dan arsip nonaktif."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.calibration_annotations import TAXONOMY_SOURCE
from evaluation.calibration_review_v4 import MANUAL_SOURCE, build_v4_workbook, prepare_review


def row(filename, decision="", source="lenient_only"):
    return {"filename": filename, "standard_name": "Nama bahan", "category": "aman",
            "matched_variant": "Nama varian", "sumber": source,
            "potongan_teks": "... Nama varian ...", "keputusan": decision,
            "ingredient_id": 1, "matched_text": "Nama varian", "relasi_taksonomi": []}


KB = [{"ingredient_id": 1, "standard_name": "Nama bahan", "category": "aman", "name_variant": "Nama varian"}]


class ReviewV4Tests(unittest.TestCase):
    def test_all_y_remain_active_while_filtered_n_and_blank_are_archived(self):
        previous = [row("kept.jpeg", "Y"), row("filtered_y.jpeg", "Y"),
                    row("filtered_n.jpeg", "N"), row("filtered_blank.jpeg")]
        candidates = [row("kept.jpeg", source=TAXONOMY_SOURCE), row("new.jpeg")]
        active, review, archived, summary = prepare_review(candidates, previous, KB)
        self.assertEqual(summary["candidate_total"], 3)
        self.assertEqual(summary["automatic_candidate_total"], 2)
        self.assertEqual(summary["manual_restored_total"], 1)
        self.assertEqual(summary["carried_y_total"], 2)
        self.assertEqual(summary["new_candidate_total"], 1)
        self.assertEqual(summary["needs_new_decision_total"], 1)
        self.assertEqual(summary["taxonomy_by_decision"], {"Y": 1})
        self.assertEqual([item["filename"] for item in archived], ["filtered_n.jpeg", "filtered_blank.jpeg"])
        restored = next(item for item in review if item["filename"] == "filtered_y.jpeg")
        self.assertEqual(restored["keputusan"], "Y")
        self.assertEqual(restored["sumber"], MANUAL_SOURCE)
        self.assertEqual(restored["status_deteksi_v4"], "DIPERTAHANKAN_MANUAL")
        self.assertEqual(restored["matched_variant"], "Nama varian")
        self.assertEqual(active[0]["sumber"], TAXONOMY_SOURCE)

    def test_restoration_refuses_unknown_variant_or_changed_category(self):
        for altered in (dict(row("a.jpeg", "Y"), matched_variant="Varian berbeda"),
                        dict(row("a.jpeg", "Y"), category="hindari")):
            with self.subTest(altered=altered):
                with self.assertRaises(ValueError):
                    prepare_review([], [altered], KB)

    def test_workbook_main_sheet_contains_only_active_rows_and_all_approved_y(self):
        previous = [row("kept.jpeg", "Y"), row("filtered_y.jpeg", "Y"), row("filtered_n.jpeg", "N")]
        active, review, archived, continuity = prepare_review([row("kept.jpeg")], previous, KB)
        summary = {"n_photos": 40, "kb_ingredients": 240, "kb_variants": 1227,
                   "old_exact_total": 362, "exact_total": 362, "kb_sha256": "test",
                   "exact_by_category": {}, "candidates_by_category": {}, "candidates_by_source": {},
                   "changes_by_type": {}, "previous_review_path": "v2.xlsx", "previous_review_sha256": "test",
                   "forbidden_typo_pairs": [["kalium", "kalsium"]], **continuity}
        workbook = build_v4_workbook({}, active, review, archived, previous[1:], summary)
        self.assertEqual(workbook["kandidat_review"].max_row - 1, 2)
        self.assertEqual(workbook["kandidat_review"]["G1"].value, "keputusan")
        self.assertEqual(workbook["kandidat_review"]["H1"].value, "status_vs_v2")
        self.assertEqual(workbook["disetujui_manual_v2"].max_row - 1, 2)
        self.assertEqual(workbook["arsip_nonaktif_v2"].max_row - 1, 1)
        self.assertEqual(workbook["terfilter_otomatis"].max_row - 1, 2)
        self.assertEqual([workbook["kandidat_review"].cell(index, 7).value for index in (2, 3)], ["Y", "Y"])


if __name__ == "__main__":
    unittest.main()
