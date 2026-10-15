"""Seed the operational KB v2 without research transcripts or expert notes.

Run Alembic migrations first, then run from backend/:
    python -m app.db.seed_knowledge_base_deploy --dry-run
    python -m app.db.seed_knowledge_base_deploy --apply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ingredient, IngredientSynonym, SafetyCategory

SOURCE_PATH = Path(__file__).with_name("knowledge_base_v2_deploy.json")
EXPECTED_INGREDIENTS = 259


def load_rows() -> list[dict]:
    data = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rows = data["ingredients"]
    if data.get("version") != "kb_v2_deploy" or len(rows) != EXPECTED_INGREDIENTS:
        raise ValueError("Berkas KB v2 deploy tidak sesuai.")
    ids = [row["id"] for row in rows]
    names = [row["standard_name"] for row in rows]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise ValueError("ID atau nama bahan tidak unik.")
    for row in rows:
        SafetyCategory(row["category"])
        if not isinstance(row["synonyms"], list):
            raise ValueError("Sinonim harus berupa daftar.")
    return rows


def apply_rows(rows: list[dict]) -> None:
    engine = create_engine(settings.DATABASE_URL)
    try:
        with Session(engine) as session:
            if session.scalar(select(func.count()).select_from(Ingredient)):
                raise RuntimeError("Tabel bahan sudah berisi data; seed deploy hanya untuk database kosong.")
            for row in rows:
                ingredient = Ingredient(
                    id=row["id"],
                    standard_name=row["standard_name"],
                    category=SafetyCategory(row["category"]),
                    justification="Kategori dari KB v2 yang telah divalidasi ahli gizi.",
                    references=None,
                    is_validated=True,
                )
                session.add(ingredient)
                for variant in row["synonyms"]:
                    session.add(IngredientSynonym(ingredient=ingredient, synonym=variant))
            session.flush()
            for table in ("ingredients", "ingredient_synonyms"):
                session.execute(text(
                    "SELECT setval(pg_get_serial_sequence(:name, 'id'), "
                    "(SELECT MAX(id) FROM " + table + "), true)"
                ), {"name": table})
            session.commit()
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = load_rows()
    if args.apply:
        apply_rows(rows)
    print(json.dumps({
        "mode": "applied" if args.apply else "dry-run",
        "ingredients": len(rows),
        "synonyms": sum(len(row["synonyms"]) for row in rows),
    }))


if __name__ == "__main__":
    main()
