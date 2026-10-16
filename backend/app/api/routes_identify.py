"""Tahap 7 - POST /identify: upload foto kemasan -> hasil klasifikasi bahan.

Pipeline per request, berurutan:
  decode -> preprocess (5 tahap) -> OCR -> tokenize -> match -> classify.

Reader EasyOCR TIDAK di-load di sini; extract_text() memakai singleton dari
Tahap 3 (app/ocr/reader.py) supaya model tidak di-load ulang tiap request.
"""

from __future__ import annotations

from io import BytesIO
from threading import BoundedSemaphore
from typing import Literal

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.classifier.rule_based import classify_product
from app.api.runtime_config import load_runtime_config
from app.db.kb_integrity import inspect_kb
from app.db.session import get_db
from app.matching.fuzzy_matcher import load_knowledge_base
from app.matching.runtime_mode import match_token_many, matcher_hashes, matcher_mode
from app.ocr.reader import extract_text
from app.preprocessing.pipeline import preprocess
from app.schemas.identify import (
    HealthResponse,
    IdentifyResponse,
    ManualIdentifyRequest,
)
from app.tokenizer.tokenizer import (
    OPEN_MARKERS, _find_closing_marker, _find_marker,
    extract_composition_section, tokenize,
)

router = APIRouter()

# Knob: batas ukuran upload. Foto HP 12MP JPEG ~5MB, jadi 10MB sudah longgar.
# Ditolak SEBELUM decode/OCR: laptop target 8GB RAM dan EasyOCR sendiri sudah
# makan ~1.5GB, jangan sampai file raksasa ikut masuk memori.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
OCR_GATE = BoundedSemaphore(1)


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Periksa koneksi, KB operasional, dan hash konfigurasi beku."""
    config = load_runtime_config()
    hashes = matcher_hashes()
    mode = matcher_mode()
    try:
        db.execute(text("SELECT 1"))
        kb = inspect_kb(db)
    except SQLAlchemyError:
        failed = HealthResponse(
            status="unhealthy", database="unavailable", kb_version="unknown",
            kb_hash=None, config_hash=config.config_sha256,
            matcher_mode=mode, frozen_matcher_hash=hashes["frozen"],
            optimized_matcher_hash=hashes["optimized"],
        )
        return JSONResponse(status_code=503, content=failed.model_dump())
    result = HealthResponse(
        status="ok" if kb.healthy else "unhealthy",
        database="ok",
        kb_version=kb.version,
        kb_hash=kb.sha256,
        config_hash=config.config_sha256,
        matcher_mode=mode,
        frozen_matcher_hash=hashes["frozen"],
        optimized_matcher_hash=hashes["optimized"],
    )
    if not kb.healthy:
        return JSONResponse(status_code=503, content=result.model_dump())
    return result


@router.post("/identify", response_model=IdentifyResponse)
def identify(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IdentifyResponse:
    """Terima foto kemasan, kembalikan verdict + bahan per kategori."""
    try:
        image = _decode_upload(file)
        config = load_runtime_config()
        with OCR_GATE:
            raw_text = extract_text(preprocess(image), max_width=config.max_ocr_width)
        return _classify_text(raw_text, db, input_source="photo")
    finally:
        file.file.close()


@router.post("/identify-manual", response_model=IdentifyResponse)
def identify_manual(
    payload: ManualIdentifyRequest,
    db: Session = Depends(get_db),
) -> IdentifyResponse:
    """Sama seperti /identify tapi dari teks yang diketik pengguna: lewati
    seluruh pipeline gambar (decode/preprocess/OCR), langsung ke tokenize.
    Response identik agar frontend memakai komponen hasil yang sama."""
    return _classify_text(payload.text, db, input_source="manual")


def _classify_text(
    raw_text: str, db: Session, *, input_source: Literal["photo", "manual"] = "photo"
) -> IdentifyResponse:
    """Tahap dari teks -> verdict, dipakai bersama /identify dan
    /identify-manual (satu-satunya sumber logika klasifikasi)."""
    # Knowledge base di-query SEKALI per request, bukan per token: match_token()
    # dipanggil puluhan kali dan tiap query ulang akan sia-sia.
    try:
        knowledge_base = load_knowledge_base(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Gagal query knowledge base: {exc}")
    if not knowledge_base:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base kosong. Jalankan seed_knowledge_base_v2 pada database baru.",
        )

    config = load_runtime_config()
    composition_text = extract_composition_section(raw_text)
    tokens = tokenize(composition_text)
    hasil = classify_product([
        match for tok in tokens for match in match_token_many(
            tok, knowledge_base,
            weights=config.weights,
            threshold=config.threshold,
            shared_heads=True,
            secondary_min_score=None,
            secondary_full_coverage=False,
            length_penalty_exponent=config.length_penalty_exponent,
        )
    ])

    opening_found = closing_found = None
    if input_source == "photo":
        words = raw_text.split()
        opening_index = _find_marker(words, OPEN_MARKERS)
        opening_found = opening_index is not None
        if opening_found:
            closing_found = _find_closing_marker(words, start=opening_index + 1) is not None

    return IdentifyResponse(
        **hasil,
        raw_text=raw_text,
        composition_text=composition_text,
        opening_marker_found=opening_found,
        closing_marker_found=closing_found,
        input_source=input_source,
    )


def decode_image_bytes(data: bytes) -> np.ndarray:
    """Decode bytes with EXIF orientation applied, returning a BGR OpenCV array."""
    try:
        with Image.open(BytesIO(data)) as pil_image:
            oriented = ImageOps.exif_transpose(pil_image).convert("RGB")
            rgb = np.asarray(oriented)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("File bukan gambar yang valid atau formatnya tidak didukung.") from exc

    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _decode_upload(file: UploadFile) -> np.ndarray:
    """Baca upload jadi array OpenCV dengan EXIF orientation diterapkan."""
    # file.size diisi Starlette sebelum body dibaca, jadi file kebesaran ditolak
    # tanpa pernah masuk memori sepenuhnya.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File terlalu besar ({file.size} byte), maksimal {MAX_UPLOAD_BYTES} byte.",
        )

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:  # jaga-jaga kalau file.size tidak tersedia
        raise HTTPException(
            status_code=400, detail=f"File terlalu besar, maksimal {MAX_UPLOAD_BYTES} byte."
        )
    if not data:
        raise HTTPException(status_code=400, detail="File kosong.")

    try:
        return decode_image_bytes(data)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc
