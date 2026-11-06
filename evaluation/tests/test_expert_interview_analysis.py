from evaluation.analyze_expert_interview import agreement_summary, cohen_kappa, likert_summary


def test_agreement_percent_and_kappa_with_dummy_labels():
    left = ["aman", "aman", "hindari", "hindari"]
    right = ["aman", "perhatian", "hindari", "hindari"]
    summary = agreement_summary(left, right)
    assert summary["n_berpasangan"] == 4
    assert summary["persen_kesepakatan"] == 75
    assert cohen_kappa(left, right) == 0.6


def test_likert_summary_with_dummy_scores():
    result = likert_summary([1, 2, 4, 3])
    assert result == {"n": 4, "mean": 2.5, "median": 2.5, "min": 1, "max": 4}


def test_empty_dummy_response_is_reported_as_missing():
    assert likert_summary([])["n"] == 0
    assert agreement_summary([], []) == {"n_berpasangan": 0, "persen_kesepakatan": None, "cohen_kappa": None}
