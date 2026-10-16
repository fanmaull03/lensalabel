"""Sidik jari varian KB yang benar-benar dipakai matcher aplikasi."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db.models import ExpertValidation
from app.matching.fuzzy_matcher import load_knowledge_base


EXPECTED_KB_SHA256 = "4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e"


def canonical_kb_sha256(rows: list[dict]) -> str:
    canonical = sorted(
        (int(row["ingredient_id"]), row["standard_name"], row["category"], row["name_variant"])
        for row in rows
    )
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KBIntegrity:
    version: str
    sha256: str
    variant_count: int
    healthy: bool


def inspect_kb(session: Session) -> KBIntegrity:
    rows = load_knowledge_base(session)
    digest = canonical_kb_sha256(rows)
    healthy = digest == EXPECTED_KB_SHA256 and len(rows) == 1289
    return KBIntegrity("v2" if healthy else "unknown", digest, len(rows), healthy)


def is_v2_database(session: Session) -> bool:
    """Cegah sinkronisasi v1 pada KB v2, termasuk seed deploy tanpa catatan ahli."""
    inspector = inspect(session.get_bind())
    if not inspector.has_table("ingredients"):
        return False
    if inspector.has_table("expert_validations") and any(
        col["name"] == "source_category" for col in inspector.get_columns("expert_validations")
    ):
        recorded = session.scalar(
            select(ExpertValidation.id).where(ExpertValidation.source_category.is_not(None)).limit(1)
        )
        if recorded is not None:
            return True
    return inspect_kb(session).healthy
