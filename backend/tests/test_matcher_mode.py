"""The deploy switch must preserve the evaluated matcher byte for byte."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from app.matching import fuzzy_matcher, fuzzy_matcher_optimized
from app.matching.runtime_mode import (
    FROZEN_MATCHER_SHA256, matcher_hashes, matcher_mode, matcher_module,
    match_token_many,
)
from app.api import routes_identify


def test_frozen_matcher_equals_eval_freeze_tag():
    root = Path(__file__).resolve().parents[2]
    tagged = subprocess.check_output(
        ["git", "show", "eval-freeze-v1:backend/app/matching/fuzzy_matcher.py"],
        cwd=root,
    )
    local = Path(fuzzy_matcher.__file__).read_bytes()
    assert local == tagged
    assert hashlib.sha256(local).hexdigest() == FROZEN_MATCHER_SHA256


def test_mode_defaults_to_frozen(monkeypatch):
    monkeypatch.delenv("MATCHER_MODE", raising=False)
    assert matcher_mode() == "frozen"
    assert matcher_module() is fuzzy_matcher


def test_optimized_mode_is_separate(monkeypatch):
    monkeypatch.setenv("MATCHER_MODE", "optimized")
    assert matcher_mode() == "optimized"
    assert matcher_module() is fuzzy_matcher_optimized
    assert matcher_hashes()["frozen"] == FROZEN_MATCHER_SHA256
    assert matcher_hashes()["optimized"] != FROZEN_MATCHER_SHA256


def test_dispatch_calls_only_selected_module(monkeypatch):
    monkeypatch.setattr(fuzzy_matcher, "match_token_many", lambda *a, **k: ["frozen"])
    monkeypatch.setattr(fuzzy_matcher_optimized, "match_token_many", lambda *a, **k: ["optimized"])
    monkeypatch.setenv("MATCHER_MODE", "frozen")
    assert match_token_many("text", []) == ["frozen"]
    monkeypatch.setenv("MATCHER_MODE", "optimized")
    assert match_token_many("text", []) == ["optimized"]


def test_invalid_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("MATCHER_MODE", "unknown")
    with pytest.raises(ValueError, match="MATCHER_MODE"):
        matcher_mode()


def test_health_reports_mode_and_both_hashes(monkeypatch):
    class Database:
        def execute(self, _query):
            return None

    monkeypatch.setenv("MATCHER_MODE", "optimized")
    monkeypatch.setattr(routes_identify, "inspect_kb", lambda db: SimpleNamespace(
        healthy=True, version="v2", sha256="abc",
    ))
    response = routes_identify.health(Database())
    assert response.matcher_mode == "optimized"
    assert response.frozen_matcher_hash == FROZEN_MATCHER_SHA256
    assert response.optimized_matcher_hash == matcher_hashes()["optimized"]
