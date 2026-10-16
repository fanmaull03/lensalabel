"""Uploaded image bytes are closed even when processing fails."""

from io import BytesIO
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

import numpy as np
import pytest

from app.api import routes_identify
from app.main import cors_origins


def test_upload_is_closed_after_identification(monkeypatch):
    upload = SimpleNamespace(file=BytesIO(b"image"))
    monkeypatch.setattr(routes_identify, "_decode_upload", lambda _: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(routes_identify, "preprocess", lambda image: image)
    monkeypatch.setattr(routes_identify, "extract_text", lambda image, max_width: "Komposisi: Air")
    monkeypatch.setattr(routes_identify, "_classify_text", lambda text, db, input_source: text)

    assert routes_identify.identify(upload, object()) == "Komposisi: Air"
    assert upload.file.closed


def test_upload_is_closed_when_processing_fails(monkeypatch):
    upload = SimpleNamespace(file=BytesIO(b"invalid"))
    monkeypatch.setattr(routes_identify, "_decode_upload", lambda _: (_ for _ in ()).throw(ValueError("invalid")))

    with pytest.raises(ValueError, match="invalid"):
        routes_identify.identify(upload, object())
    assert upload.file.closed


def test_cors_origins_come_from_environment(monkeypatch):
    monkeypatch.setenv("LENSALABEL_CORS_ORIGINS", "https://app.example, https://admin.example")
    assert cors_origins() == ["https://app.example", "https://admin.example"]


def test_only_one_ocr_runs_at_a_time(monkeypatch):
    active = 0
    peak = 0
    lock = Lock()

    def fake_ocr(image, max_width):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return "Komposisi: Air"

    monkeypatch.setattr(routes_identify, "_decode_upload", lambda _: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(routes_identify, "preprocess", lambda image: image)
    monkeypatch.setattr(routes_identify, "extract_text", fake_ocr)
    monkeypatch.setattr(routes_identify, "_classify_text", lambda text, db, input_source: text)
    uploads = [SimpleNamespace(file=BytesIO(b"image")) for _ in range(3)]

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(lambda upload: routes_identify.identify(upload, object()), uploads)) == [
            "Komposisi: Air"
        ] * 3
    assert peak == 1
    assert all(upload.file.closed for upload in uploads)
