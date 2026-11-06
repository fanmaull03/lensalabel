"""Load an evaluation configuration and enforce its release gate.

Default remains evaluation/config_frozen.json (v1). Pass config_name to load a
superseding frozen record such as evaluation/config_frozen_v2.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "evaluation" / "config_frozen.json"

REQUIRED_FIELDS = ("threshold", "weights", "length_penalty", "max_ocr_width", "adaptive_threshold")


def config_path(config_name: str | None = None) -> Path:
    return ROOT / "evaluation" / config_name if config_name else CONFIG_PATH


def load_config(*, require_frozen: bool = False, config_name: str | None = None) -> dict[str, Any]:
    path = config_path(config_name)
    if not path.is_file():
        raise FileNotFoundError(f"Konfigurasi evaluasi tidak ditemukan: {path}")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    status = str(config.get("status", "")).casefold()
    if require_frozen and status != "frozen":
        raise RuntimeError(
            f"Evaluasi/aset final ditolak: {path} berstatus {status or 'tidak diketahui'!r}; "
            "status harus 'frozen' setelah dikonfirmasi pemilik proyek."
        )
    if require_frozen and (not config.get("evaluation_gt_path") or not config.get("evaluation_gt_sha256")):
        raise ValueError("Config berstatus frozen harus mencatat evaluation_gt_path dan evaluation_gt_sha256.")
    for key in REQUIRED_FIELDS:
        if key not in config:
            raise ValueError(f"Konfigurasi {path} tidak memiliki field wajib {key!r}")
    return config
