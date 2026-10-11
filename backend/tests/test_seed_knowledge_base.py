"""Uji sinkronisasi daftar tetap dengan database SQLite terisolasi."""
import unittest
from collections import Counter

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import Base, ExpertValidation, Ingredient, IngredientSynonym, SafetyCategory
from app.db.seed_knowledge_base import FINAL_INGREDIENTS, SOURCE, _snapshot, synchronize
from app.matching.fuzzy_matcher import load_knowledge_base, match_token


class KnowledgeBaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, autoflush=False)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_source_has_all_numbered_rows_and_references(self):
        rows = SOURCE["ingredients"]
        self.assertEqual([row["number"] for row in rows], list(range(1, 241)))
        self.assertEqual(len({row["standard_name"] for row in rows}), 240)
        self.assertEqual(Counter(row["category"] for row in rows),
                         {"aman": 118, "perhatian": 80, "hindari": 42})
        for row in rows:
            self.assertLessEqual(len(row["standard_name"]), 150)
            self.assertTrue(set(row["reference_codes"]) <= SOURCE["references"].keys())
            self.assertEqual(len(row["synonyms"]), len({s.casefold() for s in row["synonyms"]}))
            self.assertTrue(all(len(s) <= 150 for s in row["synonyms"]))

    def test_empty_database_and_repeated_sync(self):
        self.assertEqual(synchronize(self.session), {"inserted": 240, "updated": 0, "removed": 0})
        self.session.commit()
        before = _snapshot(self.session)
        self.assertEqual(synchronize(self.session), {"inserted": 0, "updated": 0, "removed": 0})
        self.session.commit()
        self.assertEqual(_snapshot(self.session), before)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Ingredient)), 240)
        self.assertTrue(all(not i.is_validated for i in self.session.scalars(select(Ingredient))))

    def test_legacy_names_categories_synonyms_and_obsolete_rows(self):
        milk = Ingredient(standard_name="Susu sapi", category=SafetyCategory.HINDARI,
                          justification="lama", is_validated=True)
        benzoate = Ingredient(standard_name="Natrium Benzoat", category=SafetyCategory.PERHATIAN,
                              justification="lama", is_validated=True)
        flour = Ingredient(standard_name="Tepung terigu", category=SafetyCategory.HINDARI,
                           justification="lama", synonyms=[IngredientSynonym(synonym="Pati gandum")])
        obsolete = Ingredient(standard_name="Titanium dioksida", category=SafetyCategory.PERHATIAN,
                              justification="lama")
        self.session.add_all([milk, benzoate, flour, obsolete])
        self.session.commit()
        flour_id, milk_id, benzoate_id = flour.id, milk.id, benzoate.id
        synchronize(self.session)
        self.session.commit()
        self.session.expire_all()
        self.assertEqual(self.session.get(Ingredient, flour_id).standard_name, "Terigu / Gandum")
        self.assertNotIn("Pati gandum", [s.synonym for s in self.session.get(Ingredient, flour_id).synonyms])
        self.assertTrue(self.session.get(Ingredient, milk_id).is_validated)
        self.assertEqual(self.session.get(Ingredient, benzoate_id).category, SafetyCategory.HINDARI)
        self.assertFalse(self.session.get(Ingredient, benzoate_id).is_validated)
        self.assertIsNone(self.session.scalar(select(Ingredient).where(Ingredient.standard_name == "Titanium dioksida")))

    def test_grouped_legacy_rows_preserve_validation_history(self):
        guar = Ingredient(standard_name="Guar gum", category=SafetyCategory.AMAN, justification="lama")
        cellulose = Ingredient(standard_name="Selulosa", category=SafetyCategory.AMAN, justification="lama")
        validation = ExpertValidation(ingredient=cellulose, researcher_proposed_category=SafetyCategory.AMAN,
                                      validator_name="Validator uji", is_agreed=True)
        self.session.add_all([guar, cellulose, validation])
        self.session.commit()
        guar_id, validation_id = guar.id, validation.id
        stats = synchronize(self.session)
        self.session.commit()
        self.session.expire_all()
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(self.session.get(ExpertValidation, validation_id).ingredient_id, guar_id)
        self.assertEqual(self.session.get(Ingredient, guar_id).standard_name, "Gom arab / Selulosa bubuk / Gom guar")

    def test_rollback_does_not_change_existing_database(self):
        old = Ingredient(standard_name="Gluten", category=SafetyCategory.HINDARI, justification="lama")
        self.session.add(old)
        self.session.commit()
        before = _snapshot(self.session)
        synchronize(self.session)
        self.session.rollback()
        self.assertEqual(_snapshot(self.session), before)

    def test_runtime_matching_uses_new_categories_and_distinct_entries(self):
        synchronize(self.session)
        self.session.commit()
        kb = load_knowledge_base(self.session)
        cases = {
            "E211": ("Natrium Benzoat", "hindari"),
            "E951": ("Aspartam", "hindari"),
            "E127": ("Eritrosin", "perhatian"),
            "E955": ("Sukralosa", "aman"),
            "E407": ("Karagenan (rumput laut)", "aman"),
            "Lesitin": ("Lesitin (kedelai umumnya aman, cek sumber)", "perhatian"),
            "Wheat starch": ("Pati terigu", "hindari"),
            "Milk powder": ("Susu bubuk full cream", "hindari"),
            "Almond milk": ("Susu almond (tanpa perisa buatan)", "aman"),
            "Susu kedelai": ("Susu kedelai murni", "aman"),
            "Coconut milk": ("Santan / susu kelapa", "aman"),
            "Palm olein": (SOURCE["ingredients"][158]["standard_name"], "aman"),
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                match = match_token(token, kb)
                self.assertEqual((match.standard_name, match.category), expected)


if __name__ == "__main__":
    unittest.main()
