from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import sys

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.api import routes_identify
from app.ocr import reader
from app.schemas.identify import ManualIdentifyRequest


def test_manual_text_has_bounded_length():
    assert len(ManualIdentifyRequest(text="a" * 5000).text) == 5000
    with pytest.raises(ValidationError):
        ManualIdentifyRequest(text="a" * 5001)


def test_large_image_is_rejected_before_decode(monkeypatch):
    class ImageHeader:
        width = 5000
        height = 5000

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(routes_identify.Image, "open", lambda _: ImageHeader())
    monkeypatch.setattr(
        routes_identify.ImageOps, "exif_transpose",
        lambda _: pytest.fail("image was decoded before the dimension check"),
    )
    with pytest.raises(ValueError, match="20 megapiksel"):
        routes_identify.decode_image_bytes(b"header")


def test_database_failure_does_not_expose_connection_details(monkeypatch):
    monkeypatch.setattr(
        routes_identify,
        "load_knowledge_base",
        lambda _: (_ for _ in ()).throw(
            OperationalError("SELECT secret", {}, Exception("password=private"))
        ),
    )
    with pytest.raises(HTTPException) as error:
        routes_identify._classify_text("Komposisi: Air", object())
    assert error.value.status_code == 503
    assert "private" not in error.value.detail


def test_ready_checks_model_after_database(monkeypatch):
    monkeypatch.setattr(
        routes_identify,
        "health",
        lambda _: SimpleNamespace(status="ok"),
    )
    monkeypatch.setattr(
        routes_identify,
        "get_reader",
        lambda: (_ for _ in ()).throw(RuntimeError("model missing")),
    )
    response = routes_identify.ready(object())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    monkeypatch.setattr(routes_identify, "get_reader", lambda: object())
    assert routes_identify.ready(object()).status == "ok"


def test_reader_is_initialized_once_under_concurrent_requests(monkeypatch):
    created = []
    lock = Lock()

    def make_reader(*_, **__):
        with lock:
            created.append(object())
        return created[0]

    monkeypatch.setattr(reader, "_reader", None)
    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=make_reader))
    with ThreadPoolExecutor(max_workers=4) as pool:
        instances = list(pool.map(lambda _: reader.get_reader(), range(4)))
    assert len(created) == 1
    assert all(instance is created[0] for instance in instances)
