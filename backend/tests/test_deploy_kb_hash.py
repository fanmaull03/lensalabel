"""The operational seed payload must produce the evaluated KB fingerprint."""

from app.db.kb_integrity import EXPECTED_KB_SHA256, canonical_kb_sha256
from app.db.seed_knowledge_base_deploy import load_rows


def test_deploy_seed_matches_evaluated_variants():
    ingredients = load_rows()
    variants = [
        {
            "ingredient_id": row["id"],
            "standard_name": row["standard_name"],
            "category": row["category"],
            "name_variant": variant,
        }
        for row in ingredients
        for variant in (row["standard_name"], *row["synonyms"])
    ]

    assert len(ingredients) == 259
    assert len(variants) == 1289
    assert canonical_kb_sha256(variants) == EXPECTED_KB_SHA256
