"""Regresi identitas kimia, frasa daftar bahan, dan minyak kelapa/sawit."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.calibration_annotations import (
    FORBIDDEN_TYPO_PAIRS, TAXONOMY_SOURCE,
    is_word_fuzzy_match, lenient_occurrences, review_rows,
)


def variant(iid, name, alias=None):
    return {"ingredient_id": iid, "standard_name": name, "category": "aman",
            "name_variant": alias or name}


class LenientFilterTests(unittest.TestCase):
    def test_potassium_and_calcium_are_blocked_in_both_directions_and_derivatives(self):
        self.assertFalse(is_word_fuzzy_match("kalium", "kalsium"))
        self.assertFalse(is_word_fuzzy_match("kalsium", "kalium"))
        for suffix in ("karbonat", "klorida", "laktat"):
            for wrong, correct in (("Kalium", "Kalsium"), ("Kalsium", "Kalium")):
                with self.subTest(wrong=wrong, suffix=suffix):
                    self.assertEqual(lenient_occurrences(f"{wrong} {suffix}",
                                     [variant(1, f"{correct} {suffix}")]), [])

    def test_normal_typos_remain_supported(self):
        self.assertTrue(is_word_fuzzy_match("mononatriun", "mononatrium"))
        self.assertTrue(is_word_fuzzy_match("gliserin", "gliserinn"))
        self.assertTrue(is_word_fuzzy_match("susu", "susuu"))
        self.assertTrue(is_word_fuzzy_match("susuu", "susu"))
        self.assertFalse(is_word_fuzzy_match("garam", "garamm"))

    def test_all_confirmed_distinct_substances_are_blocked_both_ways(self):
        self.assertEqual(len(FORBIDDEN_TYPO_PAIRS), 13)
        for pair in FORBIDDEN_TYPO_PAIRS:
            left, right = sorted(pair)
            for actual, expected in ((left, right), (right, left)):
                with self.subTest(actual=actual, expected=expected):
                    self.assertFalse(is_word_fuzzy_match(actual, expected))
                    self.assertEqual(lenient_occurrences(actual, [variant(1, expected)]), [])

    def test_confirmed_spelling_and_plural_variants_stay_tolerant(self):
        pairs = (("almond", "almonds"), ("casein", "kasein"),
                 ("cokelat", "coklat"), ("extract", "extracts"),
                 ("instan", "instant"), ("phosphate", "phosphates"),
                 ("sintetik", "sintetis"), ("yoghurt", "yogurt"))
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertTrue(is_word_fuzzy_match(left, right))
                self.assertTrue(is_word_fuzzy_match(right, left))

    def test_ins_and_e_codes_only_match_identically(self):
        for actual, expected in (("ins250", "ins251"), ("ins250", "ins2500"),
                                 ("ins250", "ins25o"), ("e250", "e251"),
                                 ("123456", "123457")):
            with self.subTest(actual=actual, expected=expected):
                self.assertFalse(is_word_fuzzy_match(actual, expected))
                self.assertEqual(lenient_occurrences(actual, [variant(1, expected)]), [])
        self.assertTrue(is_word_fuzzy_match("ins250", "ins250"))
        self.assertEqual(len(lenient_occurrences("INS 250", [variant(1, "INS 250")])), 1)

    def test_spaced_ins_alias_cannot_stitch_prefix_and_number_from_different_codes(self):
        kb = [variant(1, "INS 250")]
        self.assertEqual(lenient_occurrences("INS 251 250", kb), [])
        text = "INS 251 dan INS 250"
        matches = lenient_occurrences(text, kb)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].start, text.rfind("INS"))

    def test_windows_cannot_stitch_across_list_or_parenthesis_boundaries(self):
        examples = [
            ("Susu, Kedelai, Ikan", "Susu kedelai"),
            ("Air, Gula, 3 Mineral", "Air mineral"),
            ("Perisa Sintetik, Pewarna Alami", "Perisa alami"),
            ("Perisa Sintetik (Pewarna Alami)", "Perisa alami"),
            ("Perisa Sintetik) Alami", "Perisa alami"),
            ("Tepung Terigu, Minyak Olein Kelapa", "Tepung kelapa"),
            ("Krimer Bubuk (5,5%) [Susu Bubuk Skim]", "Krimer susu bubuk"),
            ("Susu; Kedelai", "Susu kedelai"),
        ]
        for text, alias in examples:
            with self.subTest(text=text):
                self.assertEqual(lenient_occurrences(text, [variant(1, alias)]), [])

    def test_neutral_insertions_and_hyphens_still_match_within_one_phrase(self):
        examples = [
            ("Mononatriurn L-Glutamat", "Mononatrium glutamat"),
            ("Dinatrium 5'-Guanilat", "Dinatrium guanilat"),
            ("Asesulfam-K", "Asesulfam K"),
            ("Minyak Inti Kelapa Sawit", "Minyak kelapa sawit"),
        ]
        for text, alias in examples:
            with self.subTest(text=text):
                self.assertEqual(len(lenient_occurrences(text, [variant(1, alias)])), 1)
        self.assertEqual(lenient_occurrences("Mononatrium a b c d glutamat",
                         [variant(1, "Mononatrium glutamat")]), [])

    def test_decimal_comma_is_not_an_item_separator(self):
        self.assertEqual(len(lenient_occurrences("Minyak 0,5% kelapa", [variant(1, "Minyak kelapa")])), 1)

    def test_palm_specificity_includes_sawit_after_the_short_window(self):
        palm_name = "Minyak sawit / Minyak kelapa sawit"
        kb = [variant(1, "Minyak kelapa"), variant(2, palm_name, "Minyak kelapa sawit")]
        for text in ("Minyak Kelapa Sawit", "Minyak Olein Kelapa Sawit", "Minyak Inti Kelapa Sawit"):
            for variants in (kb, list(reversed(kb))):
                with self.subTest(text=text):
                    matches = lenient_occurrences(text, variants)
                    self.assertEqual({match.ingredient_id for match in matches}, {2})

    def test_specificity_does_not_suppress_separate_coconut_ingredient(self):
        kb = [variant(1, "Minyak kelapa"), variant(2, "Minyak kelapa sawit", "Minyak kelapa sawit")]
        matches = lenient_occurrences("Minyak kelapa, Minyak kelapa sawit", kb)
        self.assertEqual({match.ingredient_id for match in matches}, {1, 2})

    def test_strict_palm_entry_still_suppresses_false_lenient_coconut(self):
        palm = "Minyak sawit / Minyak kelapa sawit"
        kb = [variant(1, "Minyak kelapa"), variant(2, palm, "Minyak kelapa sawit")]
        self.assertEqual(review_rows("a.jpeg", "Minyak kelapa sawit", [{"ingredient_id": 2}], kb), [])

    def test_audited_taxonomy_is_flagged_without_suppressing_either_candidate(self):
        kb = [variant(1, "Susu sapi", "Susu"), variant(2, "Susu kedelai murni", "Susu kedelai")]
        for variants in (kb, list(reversed(kb))):
            rows = review_rows("a.jpeg", "Susu kedelai", [], variants)
            self.assertEqual({row["ingredient_id"] for row in rows}, {1, 2})
            self.assertTrue(all(row["sumber"] == TAXONOMY_SOURCE for row in rows))
            self.assertTrue(all(row["relasi_taksonomi"] for row in rows))
        # Bahan spesifik yang sudah strict tetap memberikan konteks untuk
        # review bahan pendek; kunci varian tidak berubah karena penandaan.
        rows = review_rows("a.jpeg", "Susu kedelai", [{"ingredient_id": 2}], kb)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matched_variant"], "Susu")
        self.assertEqual(rows[0]["sumber"], TAXONOMY_SOURCE)

    def test_taxonomy_label_requires_actual_same_phrase_from_audited_relation(self):
        kb = [variant(1, "Susu sapi", "Susu"), variant(2, "Susu kedelai murni", "Susu kedelai")]
        rows = review_rows("a.jpeg", "Susu, Kedelai", [], kb)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sumber"], "lenient_only")
        self.assertEqual(rows[0]["relasi_taksonomi"], [])
        unaudited = [variant(1, "Susu sapi", "Susu"), variant(2, "Belum diaudit", "Susu baru")]
        rows = review_rows("a.jpeg", "Susu baru", [], unaudited)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["sumber"] == "lenient_only" for row in rows))

    def test_negation_is_preserved_instead_of_becoming_taxonomy_source(self):
        kb = [variant(1, "Susu sapi", "Susu"), variant(2, "Susu kedelai murni", "Susu kedelai")]
        rows = review_rows("a.jpeg", "tanpa susu kedelai", [], kb)
        self.assertTrue(rows)
        self.assertTrue(all(row["sumber"] == "dibuang_negasi" for row in rows))


if __name__ == "__main__":
    unittest.main()
