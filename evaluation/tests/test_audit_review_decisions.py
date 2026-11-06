from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from evaluation.audit_review_decisions import run, shared_head_expression


def test_general_shared_head_coordination_recognizes_and_and_comma_forms():
    left = {"matched_variant": "Dinatrium Inosinat"}
    right = {"matched_variant": "Dinatrium Guanilat"}
    assert shared_head_expression("Dinatrium Inosinat dan Guanilat", left, right,
                                  (0, 18), (0, 31))
    assert shared_head_expression("Dinatrium Inosinat, Guanilat", left, right,
                                  (0, 18), (0, 27))
    flavor_left = {"matched_variant": "Perisa sintetik"}
    flavor_right = {"matched_variant": "Perisa alami"}
    assert shared_head_expression("Perisa sintetis dan alami", flavor_left, flavor_right,
                                  (0, 16), (0, 25))


def test_shared_head_recognizes_all_requested_separators_and_parenthesized_lists():
    left = {"matched_variant": "Perisa alami"}
    right = {"matched_variant": "Perisa sintetik"}
    for separator in ("&", "/", ";", ",", "dan", "atau"):
        text = f"Perisa Alami {separator} Sintetik"
        assert shared_head_expression(text, left, right, (0, 12), (0, len(text)))

    text = "Perisa (Sintetik, Alami)"
    assert shared_head_expression(text,
                                  {"matched_variant": "Perisa (Sintetik, Alami)"},
                                  {"matched_variant": "Perisa (Sintetik)"},
                                  (0, len(text)), (0, 16))


def test_calibration_review_audit_recovers_manual_collision_and_split_cases():
    review = ROOT / "dataset/ground_truth/calibration_review_v4.xlsx"
    assert review.exists()
    rows = run(review, ROOT / "dataset/ground_truth/transcripts.csv",
               ROOT / "dataset/ground_truth/calibration_ingredients_gt_final.json",
               ROOT / "evaluation/splits/calibration_set.csv")
    strict = [r for r in rows if "konflik_entri_strict_lebih_spesifik" in r.get("flag", "")]
    assert len(strict) == 8
    crossed = [r for r in rows if "melintasi_koma_atau_kurung" in r.get("flag", "")]
    assert {(r["filename"], r["standard_name"]) for r in crossed} == {
        ("datar_015.jpeg", "Bumbu rempah umumnya (paprika bubuk, thyme, kari)"),
        ("melengkung_014.jpeg", "Susu bubuk full cream"),
        ("melengkung_055.jpeg", "Krimer susu bubuk / Padatan susu (milk solids)"),
    }
