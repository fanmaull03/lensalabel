"""Regression tests for corrected additive codes against the reviewed KB v2."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from audit_kb_v2_context import evaluate, load_kb  # noqa: E402


def _actual_names(phrase: str, kb_data: tuple) -> set[str]:
    kb, numeric, by_id = kb_data
    result = evaluate(phrase, [], [], phrase, kb, numeric, by_id)
    return {row["standard_name"] for row in result["actual"]}


def test_ins_469_and_470_do_not_select_caseinate():
    kb_data = load_kb()
    for code in ("INS 469", "INS 470"):
        assert not any("kaseinat" in name.casefold() or "caseinate" in name.casefold()
                       for name in _actual_names(code, kb_data))


def test_e965_is_not_associated_with_vanillin():
    kb_data = load_kb()
    v2_vanillin = "v2-070"
    kb, numeric, by_id = kb_data
    assert all("e965" not in " ".join([item["standard_name"], *item["synonyms"]]).casefold()
               for item in by_id.values() if item["new_entry_id"] == v2_vanillin)
    assert v2_vanillin not in {
        row["new_entry_id"] for row in evaluate("E965", [], [], "E965", kb, numeric, by_id)["actual"]
    }


def test_ins_500_ii_selects_sodium_bicarbonate():
    kb, numeric, by_id = load_kb()
    result = evaluate("INS 500(ii)", ["v2-171"], [], "bicarbonate code", kb, numeric, by_id)
    assert result["pass"], result


def test_ins_924a_selects_potassium_bromate():
    kb, numeric, by_id = load_kb()
    result = evaluate("INS 924a", ["v2-069"], [], "bromate code", kb, numeric, by_id)
    assert result["pass"], result
