"""Entrypoint FastAPI - LensaLabel.

Jalankan dari folder backend/:
  uvicorn app.main:app --reload
Swagger docs: http://127.0.0.1:8000/docs
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_identify
from app.api.runtime_config import load_runtime_config
from app.db.kb_integrity import inspect_kb
from app.db.session import SessionLocal
from app.matching.runtime_mode import FROZEN_MATCHER_SHA256, matcher_hashes, matcher_mode

app = FastAPI(
    title="LensaLabel",
    description="Identifikasi bahan makanan dari foto label komposisi (OCR + fuzzy matching).",
)

# Frontend dev (Vite) dapat memakai default lokal; hosting harus menetapkan
# LENSALABEL_CORS_ORIGINS ke origin frontend yang diizinkan.
def cors_origins() -> list[str]:
    configured = os.environ.get("LENSALABEL_CORS_ORIGINS", "*")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if not origins:
        raise ValueError("LENSALABEL_CORS_ORIGINS tidak boleh kosong.")
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_identify.router)
app.state.kb_healthy = False


@app.on_event("startup")
def check_knowledge_base_at_startup() -> None:
    """Catat penyimpangan KB sejak awal; /health tetap memeriksa ulang."""
    load_runtime_config()
    matcher_mode()
    if matcher_hashes()["frozen"] != FROZEN_MATCHER_SHA256:
        raise RuntimeError("Modul matcher beku berubah dari tag eval-freeze-v1")
    try:
        with SessionLocal() as session:
            integrity = inspect_kb(session)
    except Exception:
        app.state.kb_healthy = False
        logging.getLogger(__name__).warning("Pemeriksaan KB saat startup gagal; layanan tidak sehat")
        return
    app.state.kb_healthy = integrity.healthy
    if not integrity.healthy:
        logging.getLogger(__name__).warning(
            "KB tidak sesuai versi evaluasi: hash=%s, varian=%s",
            integrity.sha256, integrity.variant_count,
        )
