"""Load the reviewed expert KB v2 draft after its source-category migration.

Run from backend/ with the configured DATABASE_URL:
  python -m app.db.seed_knowledge_base_v2 --dry-run
  python -m app.db.seed_knowledge_base_v2 --apply
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.config import settings
from app.db.models import (
    ExpertValidation, Ingredient, IngredientSynonym, SafetyCategory,
)

ROOT = Path(__file__).resolve().parents[3]
KB_V2_PATH = ROOT / "evaluation/results/kb_v2_phase2/kb_v2_review.json"
KB_V1_PATH = ROOT / "archive/kb_v1_and_gt_before_expert/knowledge_base_gfcf.json"
REVISION = "c71f3d95a620"
SPLIT_ENTRY_IDS = {"v2-028a", "v2-028b"}


def load_sources() -> tuple[dict, dict, dict[int, dict]]:
    kb_v2 = json.loads(KB_V2_PATH.read_text(encoding="utf-8"))
    kb_v1 = json.loads(KB_V1_PATH.read_text(encoding="utf-8-sig"))
    expert_rows = {int(row["old_no"]): row for row in kb_v2["expert_validation_rows"]}
    if set(expert_rows) != set(range(1, 241)):
        raise ValueError("Semua 240 baris validasi ahli harus tersedia.")
    if len(kb_v2["ingredients"]) != 259:
        raise ValueError("Jumlah entri KB v2 tidak sesuai draf yang disetujui.")
    return kb_v2, kb_v1, expert_rows


def _unique_synonyms(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _notes_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text_value = item.get("text") or item.get("note") or ""
                if text_value:
                    parts.append(str(text_value).strip())
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return _notes_text([value])
    return ""


def build_payloads() -> list[dict[str, Any]]:
    kb_v2, kb_v1, expert_rows = load_sources()
    old_references = kb_v1.get("references", {})
    entries = kb_v2["ingredients"]
    mapped_old_numbers = {
        int(old_no)
        for entry in entries
        for old_no in entry.get("old_numbers", [])
    }
    if mapped_old_numbers != set(range(1, 241)):
        raise ValueError("Pemetaan entri tidak mencakup tepat No. 1–240.")

    preferred_ids = [
        int(old_id)
        for entry in entries
        for old_id in entry.get("old_entry_ids", [])
    ]
    next_id = max(preferred_ids, default=0) + 1
    used_ids: set[int] = set()
    payloads = []
    for entry in entries:
        ingredient_id = next(
            (int(old_id) for old_id in entry.get("old_entry_ids", [])
             if int(old_id) not in used_ids),
            None,
        )
        if ingredient_id is None:
            while next_id in used_ids:
                next_id += 1
            ingredient_id = next_id
            next_id += 1
        used_ids.add(ingredient_id)

        category = SafetyCategory(entry["category"])
        source_category = entry["sumber_kategori"]
        notes = _notes_text(entry.get("alasan_klinis_catatan_ahli")) or _notes_text(entry.get("source_note"))
        if entry.get("old_numbers"):
            notes = (notes + "\n" if notes else "") + (
                "Sumber kategori: " + source_category + ". Nomor ahli: "
                + ", ".join(str(no) for no in entry["old_numbers"]) + "."
            )
        else:
            notes = (notes + "\n" if notes else "") + (
                "Entri tambahan KB v2; sumber kategori: " + source_category + "."
            )
        if entry["new_entry_id"] in SPLIT_ENTRY_IDS:
            notes = (notes + "\n" if notes else "") + (
                "Resolusi pemecahan No. 28 sesuai keputusan ahli: "
                + ("mengandung susu/whey = Hindari." if entry["new_entry_id"] == "v2-028a"
                   else "komposisi tanpa rincian = Perlu Perhatian.")
            )

        references = []
        for code in entry.get("reference_codes", []):
            ref = old_references.get(code, {})
            title = ref.get("title", "")
            url = ref.get("url", "")
            references.append(f"{code}: {title} {url}".strip())

        validations = []
        old_numbers = [int(no) for no in entry.get("old_numbers", [])]
        if old_numbers:
            for old_no in old_numbers:
                row = expert_rows[old_no]
                correction = str(row.get("expert_correction", "")).strip()
                is_agreed = True if correction.casefold() == "setuju" else False
                revised = row.get("category_expert")
                if correction.casefold() == "setuju":
                    revised = None
                if entry["new_entry_id"] in SPLIT_ENTRY_IDS:
                    revised = entry["category"]
                validation_note = row.get("clinical_note") or None
                if entry["new_entry_id"] in SPLIT_ENTRY_IDS:
                    split_note = (
                        "Penerapan keputusan pemecahan No. 28: "
                        + ("bagian mengandung susu/whey." if entry["new_entry_id"] == "v2-028a"
                           else "bagian komposisi tidak dirinci.")
                    )
                    validation_note = (validation_note + "\n" if validation_note else "") + split_note
                validations.append({
                    "validator_name": row["validator"],
                    "validator_specialization": None,
                    "validator_institution": None,
                    "researcher_proposed_category": row["category_initial"],
                    "is_agreed": is_agreed,
                    "revised_category": revised,
                    "expert_notes": validation_note,
                    "validated_at": row["validated_at"],
                    "source_category": source_category,
                })
        else:
            source_note = _notes_text(entry.get("source_note")) or _notes_text(entry.get("alasan_klinis_catatan_ahli"))
            validations.append({
                "validator_name": kb_v2["validator"],
                "validator_specialization": None,
                "validator_institution": None,
                "researcher_proposed_category": entry["category"],
                "is_agreed": True if source_category == "isian_langsung_ahli" else None,
                "revised_category": None if source_category == "isian_langsung_ahli" else entry["category"],
                "expert_notes": source_note or "Kategori dan bahan mengikuti tambahan ahli pada KB v2.",
                "validated_at": kb_v2["validated_at"],
                "source_category": source_category,
            })

        payloads.append({
            "id": ingredient_id,
            "new_entry_id": entry["new_entry_id"],
            "standard_name": entry["standard_name"],
            "category": category,
            "synonyms": _unique_synonyms(entry.get("synonyms", [])),
            "justification": notes or f"Kategori {entry['category']} ({source_category}).",
            "references": "\n".join(references) or None,
            "source_category": source_category,
            "validations": validations,
        })

    if len({row["id"] for row in payloads}) != len(payloads):
        raise ValueError("ID bahan hasil pemetaan tidak unik.")
    if len({row["standard_name"] for row in payloads}) != len(payloads):
        raise ValueError("Nama standar KB v2 tidak unik.")
    if any(not row["validations"] for row in payloads):
        raise ValueError("Setiap entri KB v2 harus memiliki expert_validation.")
    return payloads


def _check_revision(session: Session) -> None:
    current = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if current != REVISION:
        raise RuntimeError(f"Schema migration harus berada di revision {REVISION}; saat ini {current!r}.")


def replace_knowledge_base(session: Session) -> dict[str, int]:
    payloads = build_payloads()
    session.execute(delete(ExpertValidation))
    session.execute(delete(IngredientSynonym))
    session.execute(delete(Ingredient))
    session.flush()

    for payload in payloads:
        ingredient = Ingredient(
            id=payload["id"],
            standard_name=payload["standard_name"],
            category=payload["category"],
            justification=payload["justification"],
            references=payload["references"],
            is_validated=True,
        )
        session.add(ingredient)
        for synonym in payload["synonyms"]:
            session.add(IngredientSynonym(ingredient=ingredient, synonym=synonym))
        for record in payload["validations"]:
            correction = record["revised_category"]
            session.add(ExpertValidation(
                ingredient=ingredient,
                validator_name=record["validator_name"],
                validator_specialization=record["validator_specialization"],
                validator_institution=record["validator_institution"],
                researcher_proposed_category=SafetyCategory(record["researcher_proposed_category"]),
                is_agreed=record["is_agreed"],
                revised_category=SafetyCategory(correction) if correction else None,
                expert_notes=record["expert_notes"],
                validated_at=datetime.combine(date.fromisoformat(record["validated_at"]), time.min, timezone.utc),
                source_category=record["source_category"],
            ))
    session.flush()

    # Explicitly assigned legacy IDs and newly allocated IDs must remain above the sequence.
    for table in ("ingredients", "ingredient_synonyms", "expert_validations"):
        session.execute(text(
            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
            "GREATEST(COALESCE((SELECT MAX(id) FROM " + table + "), 1), 1), true)"
        ), {"table_name": table})
    return {
        "ingredients": len(payloads),
        "synonyms": sum(len(row["synonyms"]) for row in payloads),
        "expert_validations": sum(len(row["validations"]) for row in payloads),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = create_engine(settings.DATABASE_URL)
    backup_dir = ROOT / "evaluation/results/knowledge_base_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    db_snapshot = backup_dir / f"before_kb_v2_seed_{stamp}.json"
    try:
        with Session(engine, autoflush=False) as session:
            _check_revision(session)
            current = {
                "ingredients": [
                    {column.name: getattr(row, column.name).value if isinstance(getattr(row, column.name), SafetyCategory)
                     else getattr(row, column.name)
                     for column in Ingredient.__table__.columns}
                    for row in session.scalars(select(Ingredient).order_by(Ingredient.id))
                ],
                "synonyms": [
                    {column.name: getattr(row, column.name)
                     for column in IngredientSynonym.__table__.columns}
                    for row in session.scalars(select(IngredientSynonym).order_by(IngredientSynonym.id))
                ],
                "expert_validations": [
                    {column.name: getattr(row, column.name).value if isinstance(getattr(row, column.name), SafetyCategory)
                     else getattr(row, column.name)
                     for column in ExpertValidation.__table__.columns}
                    for row in session.scalars(select(ExpertValidation).order_by(ExpertValidation.id))
                ],
            }
            db_snapshot.write_text(json.dumps(current, ensure_ascii=False, default=str, indent=2) + "\n", encoding="utf-8")
            stats = replace_knowledge_base(session)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        print(json.dumps({
            "mode": "dry-run" if args.dry_run else "applied",
            **stats,
            "pre_seed_snapshot": str(db_snapshot.relative_to(ROOT)),
        }, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
