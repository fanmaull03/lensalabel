import pytest

from app.matching.fuzzy_matcher import composite_score, match_token, match_token_many


def kb(*names):
    return [dict(ingredient_id=i, standard_name=name, name_variant=name, category="aman")
            for i, name in enumerate(names)]


def positive(text, entries, **kwargs):
    return [m for m in match_token_many(text, entries, **kwargs) if m.matched]


def test_disjoint_ingredients_and_offsets():
    text = "Perisa Sintetik Susu Bubuk Garam"
    entries = kb("Perisa Sintetik", "Susu", "Susu Bubuk", "Garam")
    matches = positive(text, entries)
    assert {m.standard_name for m in matches} == {"Perisa Sintetik", "Susu Bubuk", "Garam"}
    spans = sorted((m.span_start, m.span_end) for m in matches)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert all(text[m.span_start:m.span_end] == m.matched_window for m in matches)


def test_no_stitching_across_consumed_span():
    assert {m.standard_name for m in positive("Asam Garam Sitrat", kb("Garam", "Asam Sitrat"), threshold=95)} == {"Garam"}


@pytest.mark.parametrize("text", ["Tanpa Susu Bubuk Garam", "Bebas dari Susu Bubuk Garam", "0% Susu Bubuk Garam", "Susu Bubuk free Garam"])
def test_rejected_span_does_not_revive_short_alias(text):
    assert {m.standard_name for m in positive(text, kb("Susu", "Susu Bubuk", "Garam"))} == {"Garam"}


def test_original_negation_context_and_repeated_occurrence_limitation():
    assert {m.standard_name for m in positive("Susu Bebas Laktosa", kb("Susu", "Laktosa"))} == {"Susu"}
    # Existing first-occurrence rule remains conservative for repeated aliases.
    assert not positive("Tanpa Susu kemudian Susu", kb("Susu"))
    assert len(positive("Susu Garam Susu", kb("Susu", "Garam"))) == 3


def test_threshold_boundary_and_original_first_winner():
    entries = kb("malt")
    boundary = composite_score("Salt", "malt")
    assert positive("Salt", entries, threshold=boundary)
    assert not positive("Salt", entries, threshold=boundary + .01)
    text = "Perisa Sintetik Susu Bubuk"
    entries = kb("Susu", "Susu Bubuk", "Perisa Sintetik")
    old = match_token(text, entries)
    new = positive(text, entries, shared_heads=False)[0]
    assert (old.standard_name, old.score, old.matched_window) == (new.standard_name, new.score, new.matched_window)


@pytest.mark.parametrize("first,second", [("Inosinat", "Guanilat"), ("Guanilat", "Inosinat")])
def test_shared_head_provenance(first, second):
    text = f"Dinatrium {first} dan {second} Garam"
    entries = kb("Dinatrium Inosinat", "Dinatrium Guanilat", "Garam")
    matches = positive(text, entries, threshold=100)
    assert {m.standard_name for m in matches} == {e['standard_name'] for e in entries}
    shared = next(m for m in matches if m.match_source == 'shared_head')
    assert text[shared.span_start:shared.span_end] == second
    assert text[slice(*shared.shared_head_span)] == 'Dinatrium'
    assert shared.score == 100


@pytest.mark.parametrize("text", [
    "Dinatrium Inosinat, dan Guanilat", "Dinatrium Inosinat (dan Guanilat)",
    "Dinatrium Inosinat dan (Guanilat)", "Dinatrium Inosinat dan Protein Guanilat",
    "Dinatrium Inosinat dan Guanilatt", "Natrium Inosinat dan Guanilat",
])
def test_shared_head_does_not_bridge_boundaries_or_typos(text):
    assert not any(m.match_source == 'shared_head' for m in positive(text, kb("Dinatrium Inosinat", "Dinatrium Guanilat")))


def test_shared_head_requires_both_entries_and_abstains_on_negation():
    assert not any(m.match_source == 'shared_head' for m in positive("Dinatrium Inosinat dan Guanilat", kb("Dinatrium Guanilat")))
    entries = kb("Dinatrium Inosinat", "Dinatrium Guanilat", "Garam")
    for prefix in ("Tanpa", "Bebas dari", "0%"):
        assert {m.standard_name for m in positive(f"{prefix} Dinatrium Inosinat dan Guanilat Garam", entries)} == {"Garam"}
    assert not positive("Dinatrium Inosinat dan Guanilat free", entries)


def test_unknown_policy_stays_at_token_level():
    assert not match_token_many("unreadable", [])[0].matched
    result = match_token_many("Garam xyzzy", kb("Garam"))
    assert len(result) == 1 and result[0].matched
    assert not any(m.matched for m in match_token_many("xyzzy", kb("Garam")))
