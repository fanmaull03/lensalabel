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
    matches = matcher_module().match_token_many(*args, **kwargs)
    token = args[0] if args else kwargs["token"]
    spans = sorted((m.span_start, m.span_end) for m in matches
                   if m.span_start is not None and m.span_end is not None)
    if not spans:
        return matches
    from app.matching.fuzzy_matcher import MatchResult
    end = 0
    for left, right in spans:
        if left > end:
            matches.append(MatchResult(token=token, matched=False, score=0.0,
                                       span_start=end, span_end=left))
        end = max(end, right)
    if end < len(token):
        matches.append(MatchResult(token=token, matched=False, score=0.0,
                                   span_start=end, span_end=len(token)))
    return matches


def matcher_hashes() -> dict[str, str]:
    return {
        "frozen": hashlib.sha256(Path(fuzzy_matcher.__file__).read_bytes()).hexdigest(),
        "optimized": hashlib.sha256(Path(fuzzy_matcher_optimized.__file__).read_bytes()).hexdigest(),
    }
