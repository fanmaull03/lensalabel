"""Composition text in the response must be the text sent to tokenization."""

import pytest

from app.api import routes_identify
from app.schemas.identify import ManualIdentifyRequest
from app.tokenizer.tokenizer import extract_composition_section


@pytest.mark.parametrize(
    "raw_text, expected_text, opening_found, closing_found",
    [
        (
            "Merek X Komposisi: Gula, Garam. Mengandung Alergen: Susu. Info Gizi",
            "Komposisi: Gula, Garam.",
            True,
            True,
        ),
        (
            "Merek X Komposisi: Gula, Garam. Takaran Saji 20 g",
            "Komposisi: Gula, Garam. Takaran Saji 20 g",
            True,
            False,
        ),
        (
            "Merek X\nGula, Garam. Informasi Nilai Gizi",
            "Merek X\nGula, Garam. Informasi Nilai Gizi",
            False,
            None,
        ),
    ],
)
def test_photo_response_uses_the_same_extraction_as_tokenizer(
    monkeypatch, raw_text, expected_text, opening_found, closing_found
):
    tokenized_inputs = []
    extracted_inputs = []
    extract = routes_identify.extract_composition_section

    def capture_extraction(text):
        extracted_inputs.append(text)
        return extract(text)

    monkeypatch.setattr(routes_identify, "load_knowledge_base", lambda db: [{}])
    monkeypatch.setattr(routes_identify, "extract_composition_section", capture_extraction)
    monkeypatch.setattr(
        routes_identify, "tokenize", lambda text: tokenized_inputs.append(text) or []
    )

    response = routes_identify._classify_text(raw_text, object(), input_source="photo")

    assert extracted_inputs == [raw_text]
    assert tokenized_inputs == [expected_text]
    assert response.composition_text == expected_text
    assert response.composition_text == extract_composition_section(raw_text)
    assert response.raw_text == raw_text
    assert response.opening_marker_found is opening_found
    assert response.closing_marker_found is closing_found
    assert response.input_source == "photo"


def test_manual_input_has_no_photo_marker_status(monkeypatch):
    raw_text = "Komposisi: Air, Gula. Diproduksi oleh A"
    tokenized_inputs = []
    monkeypatch.setattr(routes_identify, "load_knowledge_base", lambda db: [{}])
    monkeypatch.setattr(
        routes_identify, "tokenize", lambda text: tokenized_inputs.append(text) or []
    )

    response = routes_identify.identify_manual(
        ManualIdentifyRequest(text=raw_text), object()
    )

    assert tokenized_inputs == ["Komposisi: Air, Gula."]
    assert response.composition_text == tokenized_inputs[0]
    assert response.raw_text == raw_text
    assert response.input_source == "manual"
    assert response.opening_marker_found is None
    assert response.closing_marker_found is None
