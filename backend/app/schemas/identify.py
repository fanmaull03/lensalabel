"""Pydantic response schema untuk endpoint /identify.

Bentuknya mengikuti output classify_product() (Tahap 6) apa adanya, supaya
tidak ada penerjemahan bentuk data di tengah jalan yang bisa jadi sumber bug.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BahanCocok(BaseModel):
    """Satu bahan yang berhasil dikenali knowledge base."""

    standard_name: str
    matched_window: str | None = Field(
        default=None,
        description="Potongan teks yang benar-benar dinilai, bukan token utuh.",
    )
    score: float


class BahanTidakDikenali(BaseModel):
    """Token komposisi yang gagal di-match, tetap dilaporkan (bukan disembunyikan)."""

    token: str
    score: float
    terdekat: str | None = Field(
        default=None, description="name_variant terdekat, walau di bawah threshold."
    )


class ManualIdentifyRequest(BaseModel):
    """Body untuk /identify-manual: teks komposisi yang diketik pengguna,
    menggantikan hasil OCR. min_length=1 menolak string kosong di batas."""

    text: str = Field(min_length=1, description="Teks komposisi mentah dari pengguna.")


class IdentifyResponse(BaseModel):
    verdict: str = Field(
        description="tidak_terbaca | hindari | perhatian | perlu_verifikasi | aman"
    )
    aman: list[BahanCocok] = []
    perhatian: list[BahanCocok] = []
    hindari: list[BahanCocok] = []
    tidak_dikenali: list[BahanTidakDikenali] = []
    raw_text: str = Field(description="Teks sebelum ekstraksi: OCR foto atau input manual.")
    composition_text: str | None = Field(
        default=None, description="Teks hasil ekstraksi yang diberikan ke tokenizer."
    )
    opening_marker_found: bool | None = Field(
        default=None, description="Status penanda pembuka pada foto; null untuk input manual."
    )
    closing_marker_found: bool | None = Field(
        default=None, description="Status penanda penutup; null jika tidak diperiksa."
    )
    input_source: Literal["photo", "manual"] | None = Field(
        default=None, description="Sumber teks: foto atau input manual."
    )


class HealthResponse(BaseModel):
    status: str
    database: str
    kb_version: str | None = None
    kb_hash: str | None = None
    config_hash: str | None = None
    matcher_mode: Literal["frozen", "optimized"]
    frozen_matcher_hash: str
    optimized_matcher_hash: str
