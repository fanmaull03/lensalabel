"""Sinkronkan 240 entri tetap dari Lembar_Validasi_KB_Diet_GFCF_Autisme_final.pdf.

Kategori mengikuti Usulan Peneliti; koreksi dan tanda tangan ahli masih kosong.
Dari backend/: python -m app.db.seed_knowledge_base [--dry-run]
Data lama dicadangkan, lalu bahan dan sinonim dicerminkan dalam satu transaksi.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db.models import Base, ExpertValidation, Ingredient, IngredientSynonym, SafetyCategory

SOURCE_PATH = Path(__file__).with_name("knowledge_base_gfcf.json")
SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
if (
    [row["number"] for row in SOURCE["ingredients"]] != list(range(1, 241))
    or len({row["standard_name"] for row in SOURCE["ingredients"]}) != 240
):
    raise ValueError("Daftar tetap harus memuat tepat 240 entri unik, bernomor 1–240.")
FINAL_INGREDIENTS = [
    (
        row["standard_name"], row["synonyms"], SafetyCategory(row["category"]),
        f"Kategori usulan peneliti: {row['category']}. "
        f"Sesuai {SOURCE['source_document']}, baris {row['number']}, halaman {row['page']}. "
        f"Kode aditif pada lembar: {row['additive_codes']}. "
        "Koreksi kategori dan alasan klinis ahli belum diisi.",
    )
    for row in SOURCE["ingredients"]
]
# Kompatibilitas dengan skrip yang mengimpor nama konstanta lama.
DRAFT_INGREDIENTS = FINAL_INGREDIENTS

LEGACY_ROW_NUMBERS = {
    "Tepung terigu": 1, "Barley": 3, "Oat": 14, "Kasein": 22,
    "Keju": 17, "Whey": 21, "Sunset Yellow": 45, "Karmosin": 46,
    "Biru Berlian": 52, "Sulfit": 58, "BHA": 66, "BHT": 67, "MSG": 59,
    "Gula pasir": 147, "Fruktosa tinggi": 177, "Cokelat": 97,
    "Perisa buatan": 41, "Asam askorbat": 185, "Tokoferol": 186,
    "Beta karoten": 236, "Karagenan": 211, "Guar gum": 184,
    "Akasia gum": 184, "Selulosa": 184, "Lesitin": 38, "Gliserol": 190,
    "Mono dan digliserida": 39, "Asam sitrat": 175, "Natrium sitrat": 207,
    "Asam laktat": 210, "Asam malat": 199, "Natrium klorida": 148,
    "Kalsium fosfat": 173, "Tepung sagu": 109, "Tepung jagung": 150,
}
LEGACY_NAMES = {
    name: SOURCE["ingredients"][number - 1]["standard_name"]
    for name, number in LEGACY_ROW_NUMBERS.items()
}


def _references(row: dict) -> str:
    return "\n".join(
        f"{code}: {SOURCE['references'][code]['title']} {SOURCE['references'][code]['url']}"
        for code in row["reference_codes"]
    )


def _snapshot(session: Session) -> dict:
    """Salin seluruh kolom dan relasi agar data lama dapat dipulihkan."""
    def encode(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, SafetyCategory):
            return value.value
        return value

    return {
        model.__tablename__: [
            {column.name: encode(getattr(record, column.name)) for column in model.__table__.columns}
            for record in session.scalars(select(model).order_by(model.id))
        ]
        for model in (Ingredient, IngredientSynonym, ExpertValidation)
    }


def synchronize(session: Session) -> dict[str, int]:
    """Cerminkan sumber tetap, pertahankan ID dan audit bahan yang masih dipakai."""
    existing = list(session.scalars(
        select(Ingredient).options(
            selectinload(Ingredient.synonyms), selectinload(Ingredient.validations)
        ).order_by(Ingredient.id)
    ))
    by_name = {ingredient.standard_name: ingredient for ingredient in existing}
    retained_ids = set()
    stats = {"inserted": 0, "updated": 0, "removed": 0}

    for row, (name, synonyms, category, justification) in zip(SOURCE["ingredients"], FINAL_INGREDIENTS):
        legacy = [ingredient for ingredient in existing if LEGACY_NAMES.get(ingredient.standard_name) == name]
        ingredient = by_name.get(name)
        if ingredient is None and legacy:
            ingredient = legacy[0]
        is_new = ingredient is None
        if is_new:
            ingredient = Ingredient(standard_name=name, is_validated=False)
            session.add(ingredient)
            stats["inserted"] += 1
        else:
            retained_ids.add(ingredient.id)
            if ingredient.category != category:
                ingredient.is_validated = False

        for duplicate in legacy:
            if duplicate is not ingredient:
                for validation in list(duplicate.validations):
                    validation.ingredient = ingredient

        ingredient.standard_name = name
        ingredient.category = category
        ingredient.justification = justification
        ingredient.references = _references(row)
        wanted = set(synonyms)
        kept = set()
        for synonym in list(ingredient.synonyms):
            if synonym.synonym not in wanted or synonym.synonym in kept:
                ingredient.synonyms.remove(synonym)
            else:
                kept.add(synonym.synonym)
        for synonym in synonyms:
            if synonym not in kept:
                ingredient.synonyms.append(IngredientSynonym(synonym=synonym))
                kept.add(synonym)
        if not is_new and session.is_modified(ingredient, include_collections=True):
            stats["updated"] += 1

    for ingredient in existing:
        if ingredient.id not in retained_ids:
            session.delete(ingredient)
            stats["removed"] += 1
    return stats


def seed(*, dry_run: bool = False) -> None:
    engine = create_engine(settings.DATABASE_URL)
    if not dry_run:
        Base.metadata.create_all(engine)
    backup_path = None
    with Session(engine, autoflush=False) as session:
        snapshot = _snapshot(session)
        stats = synchronize(session)
        if dry_run:
            session.rollback()
        else:
            if any(stats.values()) and snapshot["ingredients"]:
                backup_dir = Path(__file__).resolve().parents[3] / "evaluation/results/knowledge_base_backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup_path = backup_dir / f"before_gfcf_sync_{stamp}.json"
                backup_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            session.commit()
    engine.dispose()
    print(f"{'Rencana' if dry_run else 'Selesai'}: {stats['inserted']} bahan baru, "
          f"{stats['updated']} diperbarui, {stats['removed']} bahan lama dihapus/digabungkan.")
    if backup_path:
        print(f"Cadangan sebelum perubahan: {backup_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Tampilkan rencana tanpa mengubah data.")
    seed(dry_run=parser.parse_args().dry_run)
