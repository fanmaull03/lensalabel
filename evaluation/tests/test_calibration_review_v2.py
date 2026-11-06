"""Uji struktur review v2 dan kontinuitas keputusan tanpa mengubah matcher."""
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from evaluation.generate_calibration_review_v2 import (
    REVIEW_FIELDS, build_v2_workbook, carry_decisions, read_previous_review,
)


def row(filename="a.jpeg", name="Minyak kelapa", variant="Coconut oil", decision=""):
    return {"filename": filename, "standard_name": name, "category": "aman",
            "sumber": "lenient_only", "matched_variant": variant,
            "potongan_teks": "... coconut oil ...", "keputusan": decision,
            "ingredient_id": 1, "matched_text": "coconut oil"}


class ReviewV2Tests(unittest.TestCase):
    def test_fresh_review_has_only_new_undecided_candidates(self):
        candidates = [row(), row(filename="b.jpeg", decision="Y")]
        output, summary = carry_decisions(candidates, [])
        self.assertEqual([item["status_vs_v1"] for item in output], ["BARU", "BARU"])
        self.assertTrue(all(item["keputusan"] == "" for item in output))
        self.assertEqual(summary["needs_new_decision_total"], 2)
        self.assertEqual(summary["carried_total"], 0)
        self.assertEqual(summary["lost_total"], 0)

    def test_exact_keys_carry_both_y_and_n(self):
        candidates = [row(), row(filename="b.jpeg")]
        previous = [row(decision="Y"), row(filename="b.jpeg", decision="N")]
        output, summary = carry_decisions(candidates, previous)
        self.assertEqual([item["keputusan"] for item in output], ["Y", "N"])
        self.assertTrue(all(item["status_vs_v1"] == "SAMA_DIBAWA_OTOMATIS" for item in output))
        self.assertEqual(summary["carried_total"], 2)

    def test_changed_names_variants_and_case_do_not_carry(self):
        for updated in [row(name="Minyak kelapa baru"), row(variant="Coconut Oil"), row(filename="A.jpeg")]:
            output, summary = carry_decisions([updated], [row(decision="Y")])
            self.assertEqual(output[0]["status_vs_v1"], "BARU")
            self.assertEqual(output[0]["keputusan"], "")
            self.assertEqual(output[1]["status_vs_v1"], "HILANG")
            self.assertEqual(output[1]["keputusan"], "Y")
            self.assertEqual(summary["lost_total"], 1)

    def test_workbook_has_requested_eight_columns_and_g_decision_validation(self):
        candidates = [row()]
        output, continuity = carry_decisions(candidates, [])
        summary = {
            "n_photos": 40, "kb_ingredients": 240, "kb_variants": 1227,
            "old_exact_total": 221, "exact_total": 0, "candidate_total": 1,
            "kb_sha256": "test", "exact_by_category": {}, "candidates_by_category": {},
            "candidates_by_source": {}, "changes_by_type": {},
            "previous_review_path": "", "previous_review_sha256": "", **continuity,
        }
        workbook = build_v2_workbook({}, candidates, output, summary, [])
        sheet = workbook["kandidat_review"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), REVIEW_FIELDS)
        self.assertEqual(sheet["H2"].value, "BARU")
        self.assertEqual(str(sheet.data_validations.dataValidation[0].sqref), "G2")

    def test_read_v1_uses_header_names_and_requires_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = "kandidat_review"
            fields = list(reversed(REVIEW_FIELDS[:-1]))
            previous = row(decision="y")
            sheet.append(fields)
            sheet.append([previous[field] for field in fields])
            workbook.save(path)
            self.assertEqual(read_previous_review(path)[0]["keputusan"], "Y")
            sheet.delete_cols(fields.index("matched_variant") + 1)
            workbook.save(path)
            with self.assertRaisesRegex(ValueError, "matched_variant"):
                read_previous_review(path)


if __name__ == "__main__":
    unittest.main()
