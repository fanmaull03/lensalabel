"""Uji anotasi pada transkripsi tanpa bergantung pada database/OCR."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from evaluation.calibration_annotations import review_rows, strict_ingredients
from evaluation.generate_calibration_review import regenerate


def entry(iid, name, category, variant=None):
    return {"ingredient_id": iid, "standard_name": name, "category": category,
            "name_variant": variant or name}


class CalibrationAnnotationTests(unittest.TestCase):
    def test_exact_has_word_boundaries_and_does_not_use_fuzzy_matching(self):
        kb = [entry(1, "Garam", "aman"), entry(2, "Susu", "hindari")]
        ingredients = strict_ingredients("GARAM, garam-garam, bergaram, susuu", kb)
        self.assertEqual([item["standard_name"] for item in ingredients], ["Garam"])
        self.assertEqual(ingredients[0]["matched_variant"], "Garam")

    def test_more_specific_alias_prevents_double_counting(self):
        kb = [entry(1, "Minyak kelapa", "aman"), entry(2, "Minyak sawit", "aman", "Minyak kelapa sawit"),
              entry(3, "Susu sapi", "hindari", "Milk"), entry(4, "Susu almond", "aman", "Almond milk")]
        text = "Minyak kelapa sawit, almond milk"
        for variants in [kb, list(reversed(kb))]:
            self.assertEqual({item["standard_name"] for item in strict_ingredients(text, variants)},
                             {"Minyak sawit", "Susu almond"})
        with_separate_milk = strict_ingredients(text + ", milk", kb)
        self.assertIn("Susu sapi", {item["standard_name"] for item in with_separate_milk})

    def test_negation_applies_to_the_actual_occurrence(self):
        kb = [entry(1, "Susu", "hindari")]
        for text in ["tanpa susu", "non-susu", "milk-free"]:
            variants = kb if "susu" in text else [entry(1, "Susu", "hindari", "milk")]
            with self.subTest(text=text):
                self.assertEqual(strict_ingredients(text, variants), [])
        for text in ["tanpa susu; susu", "tanpa susu, susu", "susu, tanpa susu"]:
            with self.subTest(text=text):
                self.assertEqual(len(strict_ingredients(text, kb)), 1)

    def test_zero_percent_negation_preserves_intact_decimal_units(self):
        kb = [entry(1, "Susu", "hindari")]
        for text in ["0% susu", "0,0% susu", "0.0% susu"]:
            self.assertEqual(strict_ingredients(text, kb), [])
        self.assertEqual(len(strict_ingredients("0,5% susu", kb)), 1)

    def test_lenient_keeps_the_previous_word_matching_rules(self):
        kb = [entry(1, "MSG", "perhatian", "Mononatrium glutamat")]
        text = "Penguat rasa Mononatriurn L-glutamate"
        self.assertEqual(strict_ingredients(text, kb), [])
        candidates = review_rows("a.jpeg", text, [], kb)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["sumber"], "lenient_only")
        self.assertEqual(candidates[0]["matched_text"], "Mononatriurn L-glutamate")
        self.assertEqual(candidates[0]["keputusan"], "")
        too_many_gaps = "Mononatriurn a b c d glutamate"
        self.assertEqual(review_rows("a.jpeg", too_many_gaps, [], kb), [])

    def test_exact_ids_are_not_repeated_as_lenient_candidates(self):
        kb = [entry(1, "Garam", "aman"), entry(1, "Garam", "aman", "Salt")]
        exact = strict_ingredients("Garam, salt", kb)
        self.assertEqual(len(exact), 1)
        self.assertEqual(review_rows("a.jpeg", "Garam, salt", exact, kb), [])

    def test_negated_candidates_are_not_accepted_automatically(self):
        kb = [entry(1, "Susu", "hindari")]
        candidates = review_rows("a.jpeg", "tanpa susu", [], kb)
        self.assertEqual(candidates[0]["sumber"], "dibuang_negasi")
        self.assertEqual(candidates[0]["keputusan"], "")

    def test_regenerate_only_the_split_and_refresh_categories(self):
        split = [{"filename": "a.jpeg", "category": "datar"}]
        transcripts = [
            {"filename": "a.jpeg", "category": "datar", "ground_truth_text": "Komposisi: Sukralosa, Leci"},
            {"filename": "b.jpeg", "category": "melengkung", "ground_truth_text": "Komposisi: Sukralosa"},
        ]
        kb = [entry(30, "Sukralosa", "aman"), entry(250, "Buah tropis", "aman", "Leci")]
        exact, candidates = regenerate(split, transcripts, kb)
        self.assertEqual(list(exact), ["a.jpeg"])
        self.assertEqual(exact["a.jpeg"]["ground_truth_text"], transcripts[0]["ground_truth_text"])
        self.assertEqual({item["category"] for item in exact["a.jpeg"]["ingredients"]}, {"aman"})
        self.assertEqual(candidates, [])

    def test_missing_or_duplicate_inputs_fail_before_artifact_writes(self):
        split = [{"filename": "a.jpeg", "category": "datar"}]
        transcript = {"filename": "a.jpeg", "category": "datar", "ground_truth_text": "Komposisi: Garam"}
        kb = [entry(1, "Garam", "aman")]
        with self.assertRaises(ValueError):
            regenerate(split * 2, [transcript], kb)
        with self.assertRaises(ValueError):
            regenerate(split, [transcript] * 2, kb)
        with self.assertRaises(KeyError):
            regenerate(split, [], kb)


if __name__ == "__main__":
    unittest.main()
