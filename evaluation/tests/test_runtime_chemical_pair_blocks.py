from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.matching.fuzzy_matcher import composite_score, match_token_many
from app.matching.pair_blocks import is_forbidden_pair, pair_data
from evaluation.calibration_annotations import is_word_fuzzy_match


DATA = pair_data()


@pytest.mark.parametrize("left,right", DATA["active_pairs"])
def test_each_confirmed_active_pair_is_shared_and_blocks_runtime(left, right):
    assert is_forbidden_pair(left, right)
    assert not is_word_fuzzy_match(left, right)
    kb = [{"ingredient_id": 1, "standard_name": right, "category": "aman", "name_variant": right}]
    assert not any(m.matched for m in match_token_many(left, kb, threshold=65, shared_heads=False))


@pytest.mark.parametrize("entry", DATA["expert_pair_audit"], ids=lambda r: "-".join(r["pair"]))
def test_each_expert_pair_is_activated_only_above_candidate_threshold(entry):
    left, right = entry["pair"]
    expected = entry["score"] >= DATA["candidate_threshold"] and entry["risky_in_kb"]
    assert entry["blocked"] is expected
    assert (list(sorted([left, right])) in [list(sorted(pair)) for pair in DATA["expert_distinct_pairs"]]) is expected
    assert is_forbidden_pair(left, right) is expected
    if expected:
        assert not is_word_fuzzy_match(left, right)


def test_ordinary_typo_tolerance_remains_enabled():
    assert is_word_fuzzy_match("susuu", "susu")


def test_full_compound_chemical_pair_is_rejected_by_runtime():
    kb = [{"ingredient_id": 1, "standard_name": "Kalsium karbonat", "category": "aman",
           "name_variant": "Kalsium karbonat"}]
    assert composite_score("Kalium karbonat", "Kalsium karbonat") >= 65
    assert not any(m.matched for m in match_token_many("Kalium karbonat", kb, threshold=65, shared_heads=False))
