"""Seed dan sinkronisasi v1 tidak boleh menimpa KB v2 tanpa pilihan eksplisit."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import kb_integrity
from app.db.kb_integrity import EXPECTED_KB_SHA256, KBIntegrity, is_v2_database
from app.db.models import Base, ExpertValidation, Ingredient, SafetyCategory
from app.db.seed_knowledge_base import synchronize
from app.db import sync_synonyms


def test_v2_source_category_blocks_both_legacy_writers(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ingredient = Ingredient(
            standard_name="Contoh v2", category=SafetyCategory.AMAN,
            justification="uji", is_validated=True,
        )
        db.add(ingredient)
        db.add(ExpertValidation(
            ingredient=ingredient, researcher_proposed_category=SafetyCategory.AMAN,
            source_category="isian_langsung_ahli",
        ))
        db.commit()
        assert is_v2_database(db)
        with pytest.raises(RuntimeError, match="KB v2 terdeteksi"):
            synchronize(db)
        assert db.scalar(select(func.count()).select_from(Ingredient)) == 1
        assert synchronize(db, allow_legacy=True)["inserted"] > 0
        db.rollback()

    monkeypatch.setattr(sync_synonyms, "SessionLocal", lambda: Session(engine))
    with pytest.raises(RuntimeError, match="KB v2 terdeteksi"):
        sync_synonyms.sync(apply=True)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Ingredient)) == 1
    engine.dispose()


def test_deploy_kb_without_expert_rows_is_guarded_by_hash(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'deploy.sqlite3'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        kb_integrity, "inspect_kb",
        lambda db: KBIntegrity("v2", EXPECTED_KB_SHA256, 1289, True),
    )
    with Session(engine) as db:
        assert is_v2_database(db)
    engine.dispose()
