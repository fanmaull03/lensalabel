"""Merge membaca header dan menolak keputusan aktif yang belum lengkap."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evaluation.merge_reviewed_gt import merge_candidates, read_reviewed_candidates

FIELDS = ["filename", "standard_name", "category", "sumber", "matched_variant", "potongan_teks", "keputusan", "status_vs_v2"]


def row(decision="Y", variant="Varian", status="SAMA_DIBAWA_OTOMATIS"):
    return dict(zip(FIELDS, ["a.jpeg", "Bahan", "aman", "disetujui_manual_v2", variant, "...", decision, status]))


class MergeReviewTests(unittest.TestCase):
    def read_workbook(self, rows, fields=FIELDS):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = "kandidat_review"
            sheet.append(fields)
            for item in rows:
                sheet.append([item.get(field) for field in fields])
            workbook.save(path)
            workbook.close()
            return read_reviewed_candidates(path)

    def test_header_names_work_after_reordering_and_manual_y_is_active(self):
        result = self.read_workbook([row()], list(reversed(FIELDS)))
        self.assertEqual(result[0]["keputusan"], "Y")
        self.assertEqual(result[0]["matched_variant"], "Varian")
        self.assertEqual(result[0]["sumber"], "disetujui_manual_v2")

    def test_blank_or_invalid_decision_stops_merge(self):
        for decision in (None, "", "MUNGKIN"):
            with self.subTest(decision=decision):
                with self.assertRaises(ValueError):
                    self.read_workbook([row(decision)])

    def test_archived_blank_is_ignored_and_duplicate_active_keys_fail(self):
        self.assertEqual(len(self.read_workbook([row(), row(None, "Lama", "HILANG")])), 1)
        with self.assertRaises(ValueError):
            self.read_workbook([row(), row("N")])

    def test_merge_preserves_raw_gt_and_alias_id_while_rejecting_n(self):
        strict = {"a.jpeg": {"ground_truth_text": "Asli", "composition_text": "Asli", "ingredients": []}}
        original = copy.deepcopy(strict)
        kb = [{"ingredient_id": 23, "standard_name": "Bahan", "category": "aman", "name_variant": "Varian"}]
        final, summary = merge_candidates(strict, [row()], kb)
        self.assertEqual(strict, original)
        self.assertEqual(final["a.jpeg"]["ground_truth_text"], "Asli")
        self.assertEqual(final["a.jpeg"]["ingredients"][0]["ingredient_id"], 23)
        self.assertEqual(final["a.jpeg"]["ingredients"][0]["matched_variant"], "Varian")
        self.assertEqual(summary["manual_added_total"], 1)
        final, summary = merge_candidates(strict, [row("N")], kb)
        self.assertEqual(final, strict)
        self.assertEqual(summary["final_total"], 0)

    def test_strict_entry_is_not_duplicated_and_invalid_kb_or_filename_fails(self):
        strict = {"a.jpeg": {"ingredients": [{"standard_name": "Bahan", "category": "aman"}]}}
        kb = [{"ingredient_id": 23, "standard_name": "Bahan", "category": "aman", "name_variant": "Varian"}]
        final, summary = merge_candidates(strict, [row()], kb)
        self.assertEqual(final, strict)
        self.assertEqual(summary["manual_added_total"], 0)
        with self.assertRaises(ValueError):
            merge_candidates(strict, [row(variant="Bukan varian KB")], kb)
        with self.assertRaises(ValueError):
            merge_candidates(strict, [dict(row(), filename="di_luar_split.jpeg")], kb)


if __name__ == "__main__":
    unittest.main()
