"""Opt-in post-selection guards. Rejected spans never trigger a replacement scan."""
from __future__ import annotations

import re
from rapidfuzz.fuzz import ratio

GENERIC_WORDS = frozenset('''sodium natrium potassium kalium calcium kalsium
minyak asam pemanis perisa pewarna penstabil pengemulsi flavour flavor acid oil
artificial natural sintetik buatan alami vitamin extract ekstrak powder bubuk
colour color colouring coloring vegetable nabati bahan campuran blends agent
anti antioxidant antioksidan pengawet humektan pengental emulsifier stabilizer
flavouring flavoring enhanced enhancer'''.split())


def coverage_evidence(window: str, variant: str) -> dict:
    """Ordered, one-to-one support; a word is strong at ratio >=85, or exact.

    This is lexical evidence, not chemical equivalence. INS codes are exact only.
    """
    source = re.findall(r'\w+', window.lower())
    target = re.findall(r'\w+', variant.lower())
    # LCS alignment allows extra source words but never reuses one source word.
    dp = [[[] for _ in range(len(source) + 1)] for _ in range(len(target) + 1)]
    for i, word in enumerate(target, 1):
        for j, observed in enumerate(source, 1):
            choices = [dp[i - 1][j], dp[i][j - 1]]
            strong = word == observed or (
                not any(c.isdigit() for c in word + observed) and ratio(word, observed) >= 85
            )
            if strong:
                choices.append(dp[i - 1][j - 1] + [(i - 1, j - 1)])
            dp[i][j] = max(choices, key=lambda pairs: (len(pairs), sum(ratio(target[a], source[b]) for a,b in pairs)))
    pairs = dp[-1][-1]
    supported = [target[i] for i, _ in pairs]
    return dict(variant_words=target, span_words=source, supported_words=supported,
                full_coverage=bool(target) and len(pairs) == len(target),
                generic_only=bool(supported) and all(w in GENERIC_WORDS for w in supported),
                coverage=len(pairs) / len(target) if target else 0)


def secondary_rejection(match, *, minimum_score=None, full_coverage=False, end_offset=None):
    reasons = []
    if minimum_score is not None and match.score < minimum_score:
        reasons.append('A_score')
    if full_coverage:
        evidence = coverage_evidence(match.matched_window or '', match.matched_variant or '')
        if len(evidence['variant_words']) > 1 and not evidence['full_coverage']:
            reasons.append('B_partial_coverage')
        if evidence['generic_only']:
            reasons.append('B_generic_only')
    if end_offset is not None and (match.span_end is None or match.span_end > end_offset):
        reasons.append('C_after_panel')
    return reasons


def filter_secondary_matches(matches, *, minimum_score=None, full_coverage=False, end_offset=None):
    if minimum_score is None and not full_coverage and end_offset is None:
        return matches
    output, first = [], True
    for match in matches:
        if not match.matched:
            output.append(match)
        elif first:
            output.append(match)
            first = False
        elif not secondary_rejection(match, minimum_score=minimum_score,
                                     full_coverage=full_coverage, end_offset=end_offset):
            output.append(match)
    return output


def match_composition_guarded(raw_text, knowledge_base, *, threshold=75.0,
                              secondary_min_score=None, secondary_full_coverage=False,
                              secondary_panel_guard=False):
    """Preserve original tokenization and first matches even when C is enabled."""
    from app.matching.fuzzy_matcher import match_token_many
    from app.tokenizer.tokenizer import extract_composition_section
    composition = extract_composition_section(raw_text)
    limited = extract_composition_section(raw_text, close_secondary_panels=secondary_panel_guard)
    cutoff = len(limited) if secondary_panel_guard and limited != composition else None
    result = []
    for fragment in re.finditer(r'[^,;]+', composition):
        token = re.sub(r'\s+', ' ', fragment[0]).strip()
        if len(token) < 2:
            continue
        start = fragment.start() + len(fragment[0]) - len(fragment[0].lstrip())
        matches = match_token_many(token, knowledge_base, threshold=threshold,
                                   secondary_min_score=secondary_min_score,
                                   secondary_full_coverage=secondary_full_coverage)
        result.extend(filter_secondary_matches(matches, end_offset=None if cutoff is None else cutoff - start))
    return result
