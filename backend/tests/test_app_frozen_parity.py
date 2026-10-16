"""Perubahan pada konfigurasi aplikasi harus tetap setara dengan run beku."""

import hashlib
import inspect
import json
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api import routes_identify
from app import main as app_main
from app.api.runtime_config import DEFAULT_CONFIG_PATH, load_runtime_config
from app.db.kb_integrity import KBIntegrity, EXPECTED_KB_SHA256
from app.matching.pair_blocks import pair_data
from app.preprocessing.pipeline import STAGES
from app.schemas.identify import ManualIdentifyRequest
from app.tokenizer.tokenizer import (
    ALLERGEN_DISCLAIMER_MARKERS, CLOSE_MARKERS, CLOSING_MARKER_THRESHOLD,
    MARKER_THRESHOLD, OPEN_MARKERS, SECONDARY_PANEL_MARKERS,
    WARNING_DISCLAIMER_MARKER, extract_composition_section,
)


def test_frozen_parameters_and_source_hash():
    config = load_runtime_config()
    source = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    assert config.max_ocr_width == source["max_ocr_width"] == 1500
    assert source["adaptive_threshold"] is False
    assert [name.casefold() for name, _ in STAGES] == [
        name.casefold() for name in source["preprocessing_order"]
    ]
    assert config.threshold == source["threshold"] == 75
    assert config.weights == source["weights"] == dict.fromkeys(source["weights"], 1 / 3)
    assert config.length_penalty_exponent == source["length_penalty"]["exponent"] == 0.8
    assert source["blocked_pairs"] == pair_data()["active_pairs"] + pair_data()["expert_distinct_pairs"]
    assert len(source["blocked_pairs"]) == 14
    assert config.config_sha256 == hashlib.sha256(DEFAULT_CONFIG_PATH.read_bytes()).hexdigest()
    assert MARKER_THRESHOLD == 70 and CLOSING_MARKER_THRESHOLD == 90
    assert OPEN_MARKERS == ("KOMPOSISI", "COMPOSITION", "INGREDIENTS")
    assert CLOSE_MARKERS == (
        "MENGANDUNG ALERGEN", "ALLERGEN", "DIPRODUKSI OLEH", "DIPRODUKSI DI",
        "DIPRODUKSI DENGAN", "KODE PRODUKSI", "MANUFACTURED BY",
        "MANUFACTURED IN", "MANUFACTURED WITH",
    )
    assert ALLERGEN_DISCLAIMER_MARKERS == ("LIHAT DAFTAR", "DICETAK TEBAL", "INFORMASI ALERGEN")
    assert WARNING_DISCLAIMER_MARKER == "DISARANKAN TIDAK DIKONSUMSI"
    assert SECONDARY_PANEL_MARKERS == (
        "TAKARAN SAJI", "SERVING SIZE", "INFORMASI NILAI GIZI", "NUTRITION FACTS",
        "JUMLAH PER SAJIAN", "ENERGI TOTAL", "PERSEN AKG", "KONSUMSI GULA",
    )
    assert inspect.signature(extract_composition_section).parameters["close_secondary_panels"].default is False
    assert EXPECTED_KB_SHA256 == "4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e"


def test_config_hash_mismatch_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "config_frozen.json"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    path.with_suffix(".sha256").write_text("0" * 64, encoding="utf-8")
    monkeypatch.setenv("LENSALABEL_FROZEN_CONFIG", str(path))
    load_runtime_config.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Hash konfigurasi"):
            load_runtime_config()
    finally:
        load_runtime_config.cache_clear()


def test_photo_endpoint_passes_frozen_ocr_width(monkeypatch):
    seen = []
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    monkeypatch.setattr(routes_identify, "_decode_upload", lambda _: image)
    monkeypatch.setattr(routes_identify, "preprocess", lambda array: array)
    monkeypatch.setattr(routes_identify, "extract_text", lambda array, max_width: seen.append(max_width) or "Komposisi: Air")
    monkeypatch.setattr(routes_identify, "_classify_text", lambda text, db, input_source: text)
    upload = SimpleNamespace(file=BytesIO(b"image"))
    assert routes_identify.identify(upload, object()) == "Komposisi: Air"
    assert upload.file.closed
    assert seen == [1500]


@pytest.mark.parametrize("source", ["photo", "manual"])
def test_both_text_paths_pass_explicit_frozen_matcher_settings(monkeypatch, source):
    seen = []
    monkeypatch.setattr(routes_identify, "load_knowledge_base", lambda db: [{}])
    monkeypatch.setattr(routes_identify, "tokenize", lambda text: [text])
    monkeypatch.setattr(
        routes_identify, "match_token_many",
        lambda token, kb, **kwargs: seen.append(kwargs) or [],
    )
    if source == "manual":
        result = routes_identify.identify_manual(ManualIdentifyRequest(text="Komposisi: Air"), object())
    else:
        result = routes_identify._classify_text("Komposisi: Air", object(), input_source="photo")
    config = load_runtime_config()
    assert result.composition_text == "Komposisi: Air"
    assert seen == [{
        "weights": config.weights,
        "threshold": 75,
        "shared_heads": True,
        "secondary_min_score": None,
        "secondary_full_coverage": False,
        "length_penalty_exponent": 0.8,
    }]


def test_health_reports_hashes_and_rejects_wrong_kb(monkeypatch):
    class DB:
        def execute(self, statement):
            return 1

    monkeypatch.setattr(routes_identify, "inspect_kb", lambda db: KBIntegrity("unknown", "bad", 1, False))
    response = routes_identify.health(DB())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "unhealthy"
    assert body["kb_hash"] == "bad"
    assert body["config_hash"] == load_runtime_config().config_sha256

    monkeypatch.setattr(
        routes_identify, "inspect_kb",
        lambda db: KBIntegrity("v2", EXPECTED_KB_SHA256, 1289, True),
    )
    good = routes_identify.health(DB())
    assert good.status == "ok" and good.kb_version == "v2"

    class OfflineDB:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("offline"))

    offline = routes_identify.health(OfflineDB())
    assert offline.status_code == 503
    assert json.loads(offline.body)["config_hash"] == load_runtime_config().config_sha256


def test_startup_marks_wrong_kb_unhealthy(monkeypatch, caplog):
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(app_main, "SessionLocal", Session)
    monkeypatch.setattr(app_main, "inspect_kb", lambda db: KBIntegrity("unknown", "wrong", 1, False))
    app_main.check_knowledge_base_at_startup()
    assert app_main.app.state.kb_healthy is False
    assert "KB tidak sesuai" in caplog.text
    monkeypatch.setattr(
        app_main, "inspect_kb",
        lambda db: KBIntegrity("v2", EXPECTED_KB_SHA256, 1289, True),
    )
    app_main.check_knowledge_base_at_startup()
    assert app_main.app.state.kb_healthy is True
