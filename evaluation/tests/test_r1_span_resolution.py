from evaluation.build_eval_gt_final import resolve_spans


def _items():
    return {"photo.jpeg": {"ingredients": [
        {"standard_name": "Susu sapi", "matched_variant": "Susu", "annotation_source": "strict"},
        {"standard_name": "Susu skim bubuk", "matched_variant": "Susu Skim Bubuk", "annotation_source": "strict"},
    ]}}


def test_r1_keeps_entry_when_an_independent_occurrence_exists():
    gt, rows, _ = resolve_spans(_items(), {"photo.jpeg": "Susu Skim Bubuk; Susu."}, {"photo.jpeg"}, "test")
    assert [r["standard_name"] for r in gt["photo.jpeg"]["ingredients"]] == ["Susu sapi", "Susu skim bubuk"]
    assert any("SPAN_INDEPENDEN" in r["tindakan"] for r in rows if r["aturan"] == "R1")
    assert not any(r.get("_r1_dropped") for r in rows)


def test_r1_drops_entry_only_when_all_its_spans_are_covered():
    gt, rows, _ = resolve_spans(_items(), {"photo.jpeg": "Susu Skim Bubuk."}, {"photo.jpeg"}, "test")
    assert [r["standard_name"] for r in gt["photo.jpeg"]["ingredients"]] == ["Susu skim bubuk"]
    assert len({r["_r1_dropped"] for r in rows if r.get("_r1_dropped")}) == 1
