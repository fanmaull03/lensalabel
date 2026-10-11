from dataclasses import asdict
import pytest

from app.matching.fuzzy_matcher import MatchResult, match_token_many
from app.matching.secondary_guards import coverage_evidence, filter_secondary_matches, match_composition_guarded
from app.tokenizer.tokenizer import extract_composition_section, SECONDARY_PANEL_MARKERS


def kb(*names):
    return [dict(ingredient_id=i,standard_name=n,name_variant=n,category='aman') for i,n in enumerate(names)]


def test_disabled_guards_are_identical_and_threshold_is_inclusive():
    entries=kb('Garam','Minyak zaitun')
    old=match_token_many('Garam Minyak Nabati',entries,threshold=70)
    explicit=match_token_many('Garam Minyak Nabati',entries,threshold=70,secondary_min_score=None,secondary_full_coverage=False)
    assert old==explicit and len(old)==2
    guarded=match_token_many('Garam Minyak Nabati',entries,threshold=70,secondary_min_score=80)
    assert guarded==old[:1]
    assert filter_secondary_matches(old,minimum_score=old[1].score)==old
    assert filter_secondary_matches(old,minimum_score=101)==old[:1]


def test_coverage_is_one_to_one_and_requires_specific_support():
    assert coverage_evidence('Sodium Ascorbate','Sodium caseinate')['generic_only']
    assert not coverage_evidence('Sodium Ascorbate','Sodium caseinate')['full_coverage']
    assert not coverage_evidence('Vitamin','Vitamin C')['full_coverage']
    assert coverage_evidence('Asam Askorbat','Asam askorbat')['full_coverage']
    assert not coverage_evidence('Asam Askorbat','Asam askorbat')['generic_only']
    assert not coverage_evidence('susu','susu susu')['full_coverage']
    assert not coverage_evidence('E211','E210')['full_coverage']
    assert coverage_evidence('Flavour Enhancer','Flavor enhancer')['generic_only']


def test_guards_never_rescan_rejected_span_for_another_alias():
    entries=kb('Garam','Minyak zaitun','Minyak','Nabati')
    original=match_token_many('Garam Minyak Nabati',entries,threshold=70)
    filtered=match_token_many('Garam Minyak Nabati',entries,threshold=70,secondary_full_coverage=True)
    assert filtered[0]==original[0]
    assert all(m in original for m in filtered)


@pytest.mark.parametrize('marker',SECONDARY_PANEL_MARKERS)
def test_new_markers_require_opening_and_default_is_off(marker):
    raw=f'Komposisi: Gula Garam {marker} 123 Lemak'
    assert extract_composition_section(raw)==raw
    assert extract_composition_section(raw,close_secondary_panels=True)=='Komposisi: Gula Garam'
    no_open=f'Gula Garam {marker} 123 Lemak'
    assert extract_composition_section(no_open,close_secondary_panels=True)==no_open
    before=f'{marker} 123 Komposisi: Gula Garam'
    assert extract_composition_section(before,close_secondary_panels=True)=='Komposisi: Gula Garam'


def test_salt_sodium_is_never_a_closing_marker():
    raw='Komposisi: Gula, Garam (Natrium), Susu.'
    assert extract_composition_section(raw,close_secondary_panels=True)==raw


@pytest.mark.parametrize('flag',[False,True])
@pytest.mark.parametrize('label,text,expected',[
    ('A','Komposisi: Minyak Sawit [mengandung Antioksidan TBHQ], Garam.','Komposisi: Minyak Sawit [mengandung Antioksidan TBHQ], Garam.'),
    ('B','Komposisi: Susu, Garam. Mengandung alergen, lihat daftar bahan yang dicetak tebal.','Komposisi: Susu, Garam.'),
    ('C','Komposisi: Sukralosa. Mengandung pemanis buatan, disarankan tidak dikonsumsi oleh anak-anak.','Komposisi: Sukralosa.'),
    ('D','Komposisi: Produk Fermentasi Kedelai, Garam.','Komposisi: Produk Fermentasi Kedelai, Garam.'),
    ('E','Komposisi: Gula. Kode Produksi: 123','Komposisi: Gula.'),
])
def test_closing_marker_A_to_E(label,text,expected,flag):
    assert extract_composition_section(text,close_secondary_panels=flag)==expected


def test_c_preserves_first_match_even_in_a_later_token():
    raw='Komposisi: Gula Energi Total Garam, Susu Garam'
    entries=kb('Gula','Garam','Susu')
    normal=match_composition_guarded(raw,entries,threshold=100)
    guarded=match_composition_guarded(raw,entries,threshold=100,secondary_panel_guard=True)
    # First token starts with Gula; the first winner of token 2 is Garam by KB order.
    assert len(normal)==4 and len(guarded)==2
    assert guarded==[normal[0],normal[2]]


def test_joined_spelling_only_creates_review_candidates():
    from evaluation.calibration_annotations import joined_spelling_review_rows
    entries=kb('Beta carotene','Sodium caseinate','E 160a')
    assert len(joined_spelling_review_rows('x','Betacarotene Natural',[],entries))==1
    assert not joined_spelling_review_rows('x','Beta,carotene',[],entries)
    assert not joined_spelling_review_rows('x','Beta(carotene)',[],entries)
    assert not joined_spelling_review_rows('x','Betacarotenx',[],entries)
    assert not joined_spelling_review_rows('x','tanpa Betacarotene',[],entries)
    assert not joined_spelling_review_rows('x','E160a',[],entries)
    assert not joined_spelling_review_rows('x','Betacarotene',[{'ingredient_id':0}],entries)
    reverse=joined_spelling_review_rows('x','Beta carotene Natural',[],kb('Betacarotene'))
    assert len(reverse)==1 and reverse[0]['matched_text']=='Beta carotene'
