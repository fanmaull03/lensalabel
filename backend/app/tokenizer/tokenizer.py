"""Tahap 4 - Ekstraksi rentang komposisi + regex-based tokenization.

Alur: extract_composition_section() dulu (buang tabel gizi & teks lain),
baru tokenize() (pecah per bahan). Keduanya terpisah, bukan saling gantikan.

tokenize() MURNI pemisahan:
- tidak lowercase / normalisasi case (urusan fuzzy matching)
- tidak memfilter token "nama bahan asli" vs noise semantik (urusan threshold
  fuzzy matching)
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

_SPLIT = re.compile(r"[,;]")   # pemisah antar bahan
_SPACES = re.compile(r"\s+")   # untuk rapikan spasi ganda
MIN_TOKEN_LEN = 2              # <2 char sesudah dibersihkan = sisa noise OCR

# Penanda rentang komposisi. Dicari fuzzy karena kata ini sering rusak parah
# kena OCR (mis. "Komposisi" terbaca "Kompo5isi", "KOMPCSISI").
OPEN_MARKERS = ("KOMPOSISI", "COMPOSITION", "INGREDIENTS")
CLOSE_MARKERS = ("MENGANDUNG ALERGEN", "ALLERGEN", "DIPRODUKSI", "MANUFACTURED")
MARKER_THRESHOLD = 70  # skor partial_ratio minimal supaya dianggap penanda


def _find_marker(words: list[str], markers: tuple[str, ...], start: int = 0) -> int | None:
    """Indeks kata pertama yang cocok fuzzy dengan salah satu marker, atau None.

    Sliding window per kata; lebar window mengikuti jumlah kata tiap marker.

    Pakai ratio, BUKAN partial_ratio. partial_ratio mencari kecocokan di posisi
    mana pun dalam window, jadi ia memberi skor tinggi (77-85, lolos threshold)
    untuk kasus yang jelas salah: kata "mengandung" yang muncul di TENGAH
    komposisi ("mengandung Cabe 3.2%", "mengandung susu") dianggap penanda
    penutup "MENGANDUNG ALERGEN", sehingga sisa bahan asli ikut terbuang.
    ratio membandingkan window secara utuh dan menghukum beda panjang, jadi
    kasus salah itu turun ke 59-69 (ditolak) sementara penutup asli tetap
    97-100 (diterima).
    """
    for i in range(start, len(words)):
        for marker in markers:
            window = " ".join(words[i : i + len(marker.split())]).upper()
            if fuzz.ratio(marker, window) >= MARKER_THRESHOLD:
                return i
    return None


def extract_composition_section(text: str) -> str:
    """Potong teks dari penanda pembuka sampai penanda penutup.

    Tujuannya membuang tabel nilai gizi & teks lain yang ikut terbaca OCR,
    supaya tidak salah match ke knowledge base saat fuzzy matching.

    Kalau penanda pembuka tidak ditemukan, kembalikan teks asli utuh
    (fallback aman: lebih baik ada noise daripada kehilangan data).
    """
    words = text.split()
    open_idx = _find_marker(words, OPEN_MARKERS)
    if open_idx is None:
        return text

    close_idx = _find_marker(words, CLOSE_MARKERS, start=open_idx + 1)
    return " ".join(words[open_idx:close_idx])  # close_idx None = sampai akhir


def tokenize(text: str) -> list[str]:
    """Split by koma/titik koma, bersihkan whitespace, buang token pendek/kosong."""
    tokens = []
    for raw in _SPLIT.split(text):
        cleaned = _SPACES.sub(" ", raw).strip()
        if len(cleaned) >= MIN_TOKEN_LEN:
            tokens.append(cleaned)
    return tokens
