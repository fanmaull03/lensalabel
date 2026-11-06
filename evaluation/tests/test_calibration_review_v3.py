"""Keputusan manual tetap utuh ketika aturan lenient menghilangkan kandidat."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.calibration_review_v3 import build_v3_workbook, compare_review


def row(filename, decision=""):
    return {"filename": filename, "standard_name": "Nama bahan", "category": "aman",
            "matched_variant": "Nama varian", "sumber": "lenient_only",
            "potongan_teks": "... Nama varian ...", "keputusan": decision,
            "ingredient_id": 1, "matched_text": "Nama varian"}


class ReviewV3Tests(unittest.TestCase):
    def test_lost_approved_rows_remain_y_with_separate_active_and_lost_counts(self):
        previous = [row("kept.jpeg", "Y"), row("lost_y.jpeg", "Y"),
                    row("lost_n.jpeg", "N"), row("lost_blank.jpeg")]
        candidates = [row("kept.jpeg"), row("new.jpeg")]
        review, summary = compare_review(candidates, previous)
        self.assertEqual(summary["candidate_total"], 2)
        self.assertEqual(summary["lost_total"], 3)
        self.assertEqual(summary["new_candidate_total"], 1)
        self.assertEqual(summary["lost_by_previous_decision"], {"Y": 1, "N": 1, "KOSONG": 1})
        self.assertEqual(summary["manual_approved_total"], 2)
        self.assertEqual(summary["manual_approved_filtered_total"], 1)
        self.assertEqual(sum(item["keputusan"] == "Y" for item in review), 2)
        self.assertEqual(review[0]["status_vs_v1"], "SAMA_DIBAWA_OTOMATIS")
        self.assertEqual(review[1]["keputusan"], "")

    def test_workbook_keeps_all_y_in_manual_final_sheet_and_reports_lost_rows(self):
        previous = [row("kept.jpeg", "Y"), row("lost.jpeg", "Y")]
        candidates = [row("kept.jpeg")]
        review, continuity = compare_review(candidates, previous)
        review[-1]["alasan_filter"] = "melintasi_koma_atau_kurung"
        summary = {
            "n_photos": 40, "kb_ingredients": 240, "kb_variants": 1227,
            "old_exact_total": 362, "exact_total": 362, "kb_sha256": "test",
            "exact_by_category": {}, "candidates_by_category": {}, "candidates_by_source": {},
            "changes_by_type": {}, "previous_review_path": "v2.xlsx", "previous_review_sha256": "test",
            "forbidden_typo_pairs": [["kalium", "kalsium"]], **continuity,
        }
        workbook = build_v3_workbook({}, candidates, previous, review, summary)
        self.assertEqual(workbook["kandidat_review"]["H1"].value, "status_vs_v2")
        self.assertEqual(workbook["hilang_dari_v2"].max_row - 1, 1)
        manual = workbook["disetujui_manual_v2"]
        self.assertEqual(manual.max_row - 1, 2)
        self.assertEqual([manual.cell(i, 6).value for i in (2, 3)], ["Y", "Y"])
        self.assertEqual([manual.cell(i, 7).value for i in (2, 3)],
                         ["TETAP_DI_LENIENT_V3", "TERFILTER_OTOMATIS"])


if __name__ == "__main__":
    unittest.main()
