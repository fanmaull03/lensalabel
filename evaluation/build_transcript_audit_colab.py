"""Package fresh OCR audit with frozen inputs for an optional GPU run."""
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation/results/transcript_photo_audit"


def main():
    files = [ROOT / name for name in [
        "evaluation/run_ocr_cache.py", "evaluation/audit_transcript_fresh.py",
        "evaluation/requirements-colab.txt", "evaluation/splits/evaluation_set.csv",
        "evaluation/splits/calibration_set.csv", "dataset/ground_truth/transcripts.csv",
        "backend/app/ocr/reader.py", "backend/app/preprocessing/pipeline.py",
        "backend/app/tokenizer/tokenizer.py",
        "evaluation/results/transcript_photo_audit/fresh_audit/manual_findings.json",
    ]]
    with (ROOT / "evaluation/splits/evaluation_set.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    files += [ROOT / "dataset/raw_photos" / r["category"] / r["filename"] for r in rows]
    files += sorted((ROOT / "evaluation/results/colab_v4/ocr_cache").glob("*.json"))
    assert len(rows) == 160 and len(files) == 210
    notebook = {"nbformat": 4, "nbformat_minor": 5,
                "metadata": {"colab": {"name": "transcript_photo_fresh_ocr_audit.ipynb"}, "kernelspec": {"display_name": "Python 3", "name": "python3"}, "accelerator": "GPU"}, "cells": []}
    def cell(kind, text):
        payload = {"cell_type": kind, "metadata": {}, "source": text.splitlines(keepends=True)}
        if kind == "code":
            payload.update(execution_count=None, outputs=[])
        notebook["cells"].append(payload)
    cell("markdown", "# Audit transcript terhadap OCR mentah\nPilih Runtime > Change runtime type > GPU. Upload transcript_photo_fresh_ocr_bundle.zip. Jalankan semua sel. Foto, transcript dan algoritma tidak diubah. Ini hanya OCR dan audit, bukan grid search atau tuning evaluasi.\n")
    cell("code", "from google.colab import files\nfrom pathlib import Path\nimport zipfile, json, hashlib, os\nuploaded = files.upload()\narchive = next(name for name in uploaded if name.endswith('.zip'))\nroot = Path('/content/lensalabel_transcript_audit')\nroot.mkdir(exist_ok=True)\nwith zipfile.ZipFile(archive) as z:\n    z.extractall(root)\nos.chdir(root)\nmanifest = json.loads(Path('audit_bundle_manifest.json').read_text())\nfor name, digest in manifest['sha256'].items():\n    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name\nprint('Input verified:', len(manifest['sha256']))\ndel uploaded\n")
    cell("code", "%pip install -q -r evaluation/requirements-colab.txt openpyxl\nimport torch\nassert torch.cuda.is_available(), 'Aktifkan GPU sebelum OCR 160 foto.'\nos.environ['EASYOCR_GPU'] = '1'\nprint(torch.cuda.get_device_name(0))\n")
    cell("code", "import subprocess, sys, importlib.metadata, datetime\nout = Path('evaluation/results/transcript_photo_audit')\nout.mkdir(parents=True, exist_ok=True)\nruntime = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'python': sys.version, 'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__, 'easyocr': importlib.metadata.version('easyocr'), 'max_ocr_width': 2000, 'split_size': 160}\n(out / 'colab_runtime.json').write_text(json.dumps(runtime, indent=2))\nsubprocess.run([sys.executable, '-u', 'evaluation/run_ocr_cache.py', '--split-csv', 'evaluation/splits/evaluation_set.csv', '--photos-dir', 'dataset/raw_photos', '--cache-dir', str(out / 'fresh_evaluation_ocr')], check=True)\nsubprocess.run([sys.executable, 'evaluation/audit_transcript_fresh.py'], check=True)\nfor name, digest in manifest['sha256'].items():\n    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name\nprint('Protected inputs remain unchanged')\n")
    cell("code", "import shutil\nresult = shutil.make_archive('/content/transcript_photo_fresh_ocr_results', 'zip', root_dir='evaluation/results', base_dir='transcript_photo_audit')\nfiles.download(result)\n")
    notebook_path = ROOT / "evaluation/notebooks/transcript_photo_fresh_ocr_audit.ipynb"
    notebook_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"files": len(files), "evaluation_photos": 160, "calibration_raw_caches": 40,
                "sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    archive = OUT / "transcript_photo_fresh_ocr_bundle.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
        z.writestr("audit_bundle_manifest.json", json.dumps(manifest, indent=2))
    (OUT / "colab_bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Notebook: {notebook_path}\nBundle: {archive}\nSize: {archive.stat().st_size / 2**20:.1f} MiB")


if __name__ == "__main__":
    main()
