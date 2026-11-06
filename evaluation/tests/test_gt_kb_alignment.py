from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evaluation.validate_gt_kb_alignment import load_review_decisions, validate


def test_validate_rejects_noncanonical_name_and_category_mismatch():
    gt = {
        "a.jpeg": {
            "ingredients": [
                {"standard_name": "Nama Lama", "category": "aman"},
                {"standard_name": "Bahan KB", "category": "hindari"},
            ]
        }
    }
    kb = {"Bahan KB": {"standard_name": "Bahan KB", "category": "aman"}}

    result = validate(gt, kb, {"a.jpeg"})

    assert not result["valid"]
    assert {error["error"] for error in result["errors"]} == {
        "nama_tidak_ada_di_kb_v2",
        "kategori_gt_tidak_sama_dengan_kb_v2",
    }


def test_validate_accepts_canonical_name_and_matching_category():
    gt = {"a.jpeg": {"ingredients": [{"standard_name": "Bahan KB", "category": "aman"}]}}
    kb = {"Bahan KB": {"standard_name": "Bahan KB", "category": "aman"}}

    result = validate(gt, kb, {"a.jpeg"})

    assert result["valid"]
    assert result["items"] == 1
    assert result["categories"] == {"aman": 1}


def test_load_review_decisions_reports_pending_cases():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "review.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "validasi_kasus"
        sheet.append(["id_kasus", "keputusan_final"])
        sheet.append(["MAP-01", "v2-028b"])
        sheet.append(["MAP-02", ""])
        workbook.save(path)
        workbook.close()

        decisions, pending = load_review_decisions(path)

    assert decisions == {"MAP-01": "v2-028b", "MAP-02": ""}
    assert pending == ["MAP-02"]
