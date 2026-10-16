"""Exercise the smoke client against a local HTTP server on three calibration photos.

OCR is replayed from the stored calibration cache so this validates the HTTP,
API, matcher, and smoke comparison path without model or platform OCR drift.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import uvicorn

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.api import routes_identify
from app.db.session import get_db
from app.main import app

SAMPLES = ("datar_004.jpeg", "datar_015.jpeg", "datar_095.jpeg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.research_root
    with (root / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        ocr = {r["filename"]: r["ocr_text"] for r in csv.DictReader(stream)
               if r["config_key"] == "width_1500_adaptive_off" and r["filename"] in SAMPLES}
    if len(ocr) != len(SAMPLES):
        raise ValueError("Tiga teks OCR kalibrasi tidak tersedia")
    folder = root / "dataset/raw_photos/datar"
    digest_to_name = {hashlib.sha256((folder / name).read_bytes()).hexdigest(): name
                      for name in SAMPLES}
    kb_source = json.loads((BACKEND / "app/db/knowledge_base_v2_deploy.json").read_text(encoding="utf-8"))
    kb = [{"ingredient_id": r["id"], "standard_name": r["standard_name"],
           "category": r["category"], "name_variant": variant}
          for r in kb_source["ingredients"] for variant in [r["standard_name"], *r["synonyms"]]]
    app.dependency_overrides[get_db] = lambda: object()
    routes_identify.load_knowledge_base = lambda db: kb
    routes_identify.preprocess = lambda image: image

    def replay_decode(upload):
        digest = hashlib.sha256(upload.file.read()).hexdigest()
        index = SAMPLES.index(digest_to_name[digest])
        return np.array([[[index, 0, 0]]], dtype=np.uint8)

    routes_identify._decode_upload = replay_decode
    routes_identify.extract_text = lambda image, max_width: ocr[SAMPLES[int(image[0, 0, 0])]]
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError("Server lokal tidak mulai")
    try:
        with tempfile.TemporaryDirectory(prefix="lensalabel_smoke_") as directory:
            mapping = Path(directory) / "mapping.csv"
            with mapping.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("photo_file", "cache_filename"))
                writer.writerows((name, name) for name in SAMPLES)
            command = [sys.executable, str(BACKEND / "tools/deploy_smoke_test.py"),
                       "--url", f"http://127.0.0.1:{port}", "--photos", str(folder),
                       "--expected", str(root / "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl"),
                       "--mapping", str(mapping), "--output", str(args.output)]
            subprocess.run(command, check=True)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
