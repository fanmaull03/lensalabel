"""Parameter aplikasi yang mengikuti konfigurasi evaluasi beku."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path

from app.matching.pair_blocks import pair_data
from app.preprocessing.pipeline import STAGES


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "deploy/config_frozen.json"


@dataclass(frozen=True)
class RuntimeConfig:
    max_ocr_width: int
    threshold: float
    weights: dict[str, float]
    length_penalty_exponent: float
    config_sha256: str


@lru_cache(maxsize=1)
def load_runtime_config() -> RuntimeConfig:
    path = Path(os.environ.get("LENSALABEL_FROZEN_CONFIG", DEFAULT_CONFIG_PATH))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = path.with_suffix(".sha256")
    recorded = sidecar.read_text(encoding="utf-8-sig").strip().split()[0]
    if digest.casefold() != recorded.casefold():
        raise RuntimeError("Hash konfigurasi beku tidak cocok dengan berkas .sha256.")
    config = json.loads(raw.decode("utf-8-sig"))
    if config.get("status") != "frozen" or config.get("kb_version") != "v2":
        raise RuntimeError("Aplikasi memerlukan konfigurasi KB v2 berstatus frozen.")
    stages = [name.casefold() for name, _ in STAGES]
    if [str(name).casefold() for name in config["preprocessing_order"]] != stages:
        raise RuntimeError("Urutan preprocessing berbeda dari konfigurasi beku.")
    if config["adaptive_threshold"] is not False:
        raise RuntimeError("Adaptive threshold pada konfigurasi beku tidak didukung jalur API.")
    if config["length_penalty"]["formula"] != "(min_length / max_length) ** exponent":
        raise RuntimeError("Rumus penalti panjang berbeda dari matcher beku.")
    blocked = pair_data()
    if config["blocked_pairs"] != blocked["active_pairs"] + blocked["expert_distinct_pairs"]:
        raise RuntimeError("Daftar pasangan terlarang berbeda dari konfigurasi beku.")
    weights = {name: float(value) for name, value in config["weights"].items()}
    if set(weights) != {"levenshtein", "jaro_winkler", "ngram"} or abs(sum(weights.values()) - 1) > 1e-9:
        raise RuntimeError("Bobot komposit dalam konfigurasi beku tidak valid.")
    width = int(config["max_ocr_width"])
    if width <= 0:
        raise RuntimeError("Lebar OCR dalam konfigurasi beku tidak valid.")
    return RuntimeConfig(
        max_ocr_width=width,
        threshold=float(config["threshold"]),
        weights=weights,
        length_penalty_exponent=float(config["length_penalty"]["exponent"]),
        config_sha256=digest,
    )
