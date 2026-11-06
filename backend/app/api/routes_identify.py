"""Tahap 7 - POST /identify: upload foto kemasan -> hasil klasifikasi bahan.

Pipeline per request, berurutan:
  decode -> preprocess (5 tahap) -> OCR -> tokenize -> match -> classify.

Reader EasyOCR TIDAK di-load di sini; extract_text() memakai singleton dari
Tahap 3 (app/ocr/reader.py) supaya model tidak di-load ulang tiap request.
"""

from __future__ import annotations

from io import BytesIO
import re
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
from app.matching.fuzzy_matcher import load_knowledge_base, match_token_many
from app.ocr.reader import extract_text
from app.preprocessing.pipeline import preprocess
from app.schemas.identify import (
    HealthResponse,
    IdentifyResponse,
    ManualIdentifyRequest,
)
from app.tokenizer.tokenizer import extract_composition_with_metadata, tokenize

router = APIRouter()

# Knob: batas ukuran upload. Foto HP 12MP JPEG ~5MB, jadi 10MB sudah longgar.
# Ditolak SEBELUM decode/OCR: laptop target 8GB RAM dan EasyOCR sendiri sudah
# makan ~1.5GB, jangan sampai file raksasa ikut masuk memori.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Periksa koneksi, KB operasional, dan hash konfigurasi beku."""
    config = load_runtime_config()
    try:
        db.execute(text("SELECT 1"))
        kb = inspect_kb(db)
    except SQLAlchemyError:
        failed = HealthResponse(
            status="unhealthy", database="unavailable", kb_version="unknown",
            kb_hash=None, config_hash=config.config_sha256,
        )
        return JSONResponse(status_code=503, content=failed.model_dump())
    result = HealthResponse(
        status="ok" if kb.healthy else "unhealthy",
        database="ok",
        kb_version=kb.version,
        kb_hash=kb.sha256,
        config_hash=config.config_sha256,
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
    image = _decode_upload(file)
    config = load_runtime_config()
    raw_text = extract_text(preprocess(image), max_width=config.max_ocr_width)
    return _classify_text(raw_text, db, input_source="photo")


@router.post("/identify-manual", response_model=IdentifyResponse)
def identify_manual(
    payload: ManualIdentifyRequest,
    db: Session = Depends(get_db),
) -> IdentifyResponse:
    """Sama seperti /identify tapi dari teks yang diketik pengguna: lewati
    seluruh pipeline gambar (decode/preprocess/OCR), langsung ke tokenize.
    Response identik agar frontend memakai komponen hasil yang sama."""
    return _classify_text(payload.text, db, input_source="manual")


def _strip_opening_marker(tokens: list[str]) -> list[str]:
    """Buang kata marker pembuka ("Komposisi", "Ingredients", dsb.) dari token
    pertama TANPA membuang bahan pertama yang sah.

    Heuristik lama memotong kata pertama apa adanya, sehingga dua kasus OCR
    membuang bahan pertama: (a) marker menyatu dengan bahan ("KomposisiGula"),
    (b) marker muncul lebih dulu di kalimat lain ("Baca komposisi ...").
    Di sini kata pertama hanya dibuang kalau memang cocok fuzzy dengan marker
    (skor >= MARKER_THRESHOLD); kalau menyatu dengan bahan, hanya awalan yang
    cocok marker yang dipotong, sisanya dipertahankan.
    """
    from rapidfuzz import fuzz

    from app.tokenizer.tokenizer import MARKER_THRESHOLD, OPEN_MARKERS

    first = tokens[0]
    first_word = first.split(maxsplit=1)[0]
    # Buang semua tanda baca, bukan hanya di ujung: "Komposisi:Garam" yang
    # menyatu harus dinilai dari hurufnya saja supaya tidak kepicut cabang
    # marker-utuh (skor "KOMPOSISI:GARAM" vs "KOMPOSISI" = 75, di atas
    # threshold, padahal ada bahan menempel).
    first_word_alpha = re.sub(r"[^A-Za-z0-9]", "", first_word).upper()

    def _matches_marker(word: str) -> bool:
        return any(
            fuzz.ratio(marker, word) >= MARKER_THRESHOLD for marker in OPEN_MARKERS
        )

    if first_word_alpha in OPEN_MARKERS:
        # Kasus normal: kata pertama persis marker -> buang kata itu saja.
        # Potong juga tanda ":" yang menempel pada marker. Harus cocok PERSIS,
        # bukan fuzzy: "KomposisiGaram" skor fuzzynya 78 (di atas threshold)
        # padahal ada bahan menempel — kasus itu ditangani cabang prefix di
        # bawah.
        remainder = first[len(first_word):].lstrip(" :")
        return [remainder, *tokens[1:]] if remainder else list(tokens[1:])

    # Kasus marker menyatu dengan bahan ("KomposisiGula", "Komposisi:Garam",
    # "Ingredients:sugar"): cari awalan yang cocok marker berdasarkan HURUF
    # saja (abaikan ":" yang menempel), potong awalan itu, pertahankan sisa
    # sebagai bahan. Skor fuzzy tidak monoton terhadap panjang prefix, jadi
    # jangan berhenti di kecocokan terpanjang — pilih prefix dengan skor
    # tertinggi (marker utuh selalu menang atas potongan yang lebih panjang).
    compact = first.lstrip()
    letters = re.match(r"[A-Za-z]+", compact)
    if letters:
        word = letters.group(0).upper()
        candidates = [
            (max(fuzz.ratio(marker, word[:cut]) for marker in OPEN_MARKERS), cut)
            for cut in range(4, len(word) + 1)
        ]
        best = max(
            (c for c in candidates if c[0] >= MARKER_THRESHOLD),
            key=lambda c: (c[0], -c[1]),
            default=None,
        )
        if best is not None:
            remainder = compact[best[1]:].lstrip(" :")
            return [remainder, *tokens[1:]] if remainder else list(tokens[1:])

    # Kata pertama bukan marker (marker ada di posisi lain): jangan potong apa
    # pun, lebih baik marker tersisa sebagai noise daripada bahan terbuang.
    return tokens


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
    extraction = extract_composition_with_metadata(raw_text)
    tokens = tokenize(extraction.text)
    if extraction.opening_found and tokens:
        tokens = _strip_opening_marker(tokens)
        tokens = [token for token in tokens if token]
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
    if input_source == "photo" and not extraction.opening_found and hasil["verdict"] == "aman":
        hasil["verdict"] = "perlu_verifikasi"

    return IdentifyResponse(
        **hasil,
        raw_text=raw_text,
        composition_text=extraction.text,
        opening_marker_found=extraction.opening_found if input_source == "photo" else None,
        closing_marker_found=extraction.closing_found if input_source == "photo" else None,
        input_source=input_source,
    )


def decode_image_bytes(data: bytes) -> np.ndarray:
    """Decode bytes with EXIF orientation applied, returning a BGR OpenCV array."""
    try:
        with Image.open(BytesIO(data)) as pil_image:
            oriented = ImageOps.exif_transpose(pil_image).convert("RGB")
            rgb = np.asarray(oriented)
    except Image.DecompressionBombError as exc:
        # BUKAN subclass OSError: gambar kecil terkompresi bisa ter-dekompresi
        # melebihi MAX_IMAGE_PIXELS. Tanpa except ini, upload lolos validasi
        # ukuran tapi melempar 500.
        raise ValueError(
            "Resolusi gambar terlalu besar untuk diproses dengan aman."
        ) from exc
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
