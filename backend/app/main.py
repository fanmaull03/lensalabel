"""Entrypoint FastAPI - LensaLabel.

Jalankan dari folder backend/:
  uvicorn app.main:app --reload
Swagger docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_identify

app = FastAPI(
    title="LensaLabel",
    description="Identifikasi bahan makanan dari foto label komposisi (OCR + fuzzy matching).",
)

# Frontend dev (Vite) jalan di origin lain (localhost:5173); tanpa CORS
# browser memblokir fetch ke /identify. allow_origins="*" cukup untuk
# aplikasi lokal skripsi, tidak ada data sensitif per-user.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_identify.router)
