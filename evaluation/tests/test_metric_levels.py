from __future__ import annotations

from evaluation.evaluate_160_metrics import (
    bootstrap_summary,
    metric_triplet,
    ocr_hypothesis,
    strongest_category,
    system_status_cross_tab,
    verdict_stats,
)


def fixture_records():
    return [
        {"condition": "datar", "gt_names": {"A"}, "pred_names": {"A"},
         "gt_categories": {"hindari"}, "pred_categories": {"hindari"},
         "_gt_categories": {"hindari"}, "_pred_categories": {"hindari"},
         "category_by_name": {"A": "hindari"}, "gt_verdict": "hindari", "pred_verdict": "hindari",
         "system_status": "hindari"},
        {"condition": "melengkung", "gt_names": {"B"}, "pred_names": {"A"},
         "gt_categories": {"aman"}, "pred_categories": {"hindari"},
         "_gt_categories": {"aman"}, "_pred_categories": {"hindari"},
         "category_by_name": {"A": "hindari", "B": "aman"}, "gt_verdict": "aman", "pred_verdict": "perhatian",
         "system_status": "tidak_terbaca"},
    ]


def test_three_metric_levels_and_ci_bootstrap():
    rows = fixture_records()
    assert metric_triplet(rows, "ingredient") == (0.5, 0.5, 0.5)
    assert metric_triplet(rows, "category", "hindari") == (0.5, 1.0, 2 / 3)
    assert strongest_category({"aman", "perhatian", "hindari"}) == "hindari"
    _, _, _, matrix = verdict_stats(rows)
    assert matrix[2][2] == 1
    cross_tab = system_status_cross_tab(rows)
    assert len(cross_tab) == 15
    assert next(r for r in cross_tab if r["status_sistem"] == "tidak_terbaca" and r["verdict_gt"] == "aman")["jumlah"] == 1
    assert sum(r["jumlah"] for r in cross_tab if r["status_sistem"] == "tidak_terbaca") == 1
    assert sum(r["jumlah"] for r in system_status_cross_tab(rows, scope="datar")) == 1
    summary, confusion = bootstrap_summary(rows, iterations=100, seed=42)
    assert any(r["level"] == "ingredient" and r["kategori"] == "hindari" for r in summary)
    assert any(r["level"] == "category" and r["cakupan"] == "melengkung" for r in summary)
    assert any(r["verdict_gt"] == "hindari" and r["verdict_prediksi"] == "hindari" for r in confusion)
    assert all(r["ci95_bawah"] <= r["ci95_atas"] for r in summary + confusion)


def test_transcript_can_replace_ocr_input_explicitly():
    transcripts = {"sample.jpeg": "Teks transkrip acuan"}
    ocr = {"sample.jpeg": {"ocr_text": "Hasil OCR"}}
    assert ocr_hypothesis("sample.jpeg", transcripts, ocr, transcript_mode=True) == "Teks transkrip acuan"
    assert ocr_hypothesis("sample.jpeg", transcripts, ocr, transcript_mode=False) == "Hasil OCR"
