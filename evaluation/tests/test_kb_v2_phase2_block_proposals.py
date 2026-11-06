"""Confirmed false-identity blocks for lenient ground-truth annotation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from evaluation.calibration_annotations import FORBIDDEN_TYPO_PAIRS, is_word_fuzzy_match  # noqa: E402


def _is_forbidden(left: str, right: str) -> bool:
    return frozenset({left.casefold(), right.casefold()}) in FORBIDDEN_TYPO_PAIRS


def test_confirmed_minimal_pair_blocks():
    for left, right in (
        ("lembaga", "tembaga"),
        ("jelai", "selai"),
        ("goat", "oat"),
    ):
        assert _is_forbidden(left, right)
        assert not is_word_fuzzy_match(left, right)
        assert not is_word_fuzzy_match(right, left)
