"""Shared chemical-identity exceptions for annotation and runtime matching."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


_DATA = Path(__file__).with_name("chemical_pair_blocks.json")


@lru_cache(maxsize=1)
def pair_data() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"\w+", text, re.UNICODE)}


def is_forbidden_pair(observed: str, variant: str) -> bool:
    left, right = _words(observed), _words(variant)
    groups = pair_data()
    pairs = groups["active_pairs"] + groups["expert_distinct_pairs"]
    return any((a in left and b in right) or (b in left and a in right) for a, b in pairs)
