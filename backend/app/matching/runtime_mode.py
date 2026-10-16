"""Select the frozen or optimized matcher without modifying either module."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.matching import fuzzy_matcher, fuzzy_matcher_optimized


FROZEN_MATCHER_SHA256 = "289686a7a8a0bdf3528cfde1605b8c3633f8e82e29a752fb1c737390f5c2af13"
MATCHER_MODES = {"frozen", "optimized"}


def matcher_mode() -> str:
    mode = os.environ.get("MATCHER_MODE", "frozen").strip().lower()
    if mode not in MATCHER_MODES:
        raise ValueError("MATCHER_MODE harus 'frozen' atau 'optimized'.")
    return mode


def matcher_module():
    return fuzzy_matcher_optimized if matcher_mode() == "optimized" else fuzzy_matcher


def match_token_many(*args, **kwargs):
    return matcher_module().match_token_many(*args, **kwargs)


def matcher_hashes() -> dict[str, str]:
    return {
        "frozen": hashlib.sha256(Path(fuzzy_matcher.__file__).read_bytes()).hexdigest(),
        "optimized": hashlib.sha256(Path(fuzzy_matcher_optimized.__file__).read_bytes()).hexdigest(),
    }
