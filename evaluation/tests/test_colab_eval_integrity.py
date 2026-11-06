from __future__ import annotations

import hashlib

import pytest

from evaluation.colab_evaluate_160_ocr import verify_sha256


def test_ocr_evaluator_hash_guard_accepts_matching_bytes(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"status":"frozen"}', encoding="utf-8")
    verify_sha256(path, hashlib.sha256(path.read_bytes()).hexdigest(), "config")


def test_ocr_evaluator_hash_guard_rejects_mismatch(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"status":"draft"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="Hash config tidak cocok"):
        verify_sha256(path, "0" * 64, "config")
