"""Package tracked files from a frozen evaluation tag plus verified evaluation photos."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TAG = "eval-freeze-v1"
CONFIG_NAME = "config_frozen.json"
SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
MANIFEST = ROOT / "dataset/photo_manifest.csv"
PHOTOS = ROOT / "dataset/raw_photos"
OUTPUT = ROOT / "evaluation/results/lensalabel_eval_freeze_v1_colab.zip"


def verified_photo_bytes(root: Path, split_path: Path, manifest_path: Path, *, expected_count: int = 160) -> list[tuple[str, bytes]]:
    split = list(csv.DictReader(split_path.open(encoding="utf-8-sig", newline="")))
    if len(split) != expected_count or len({r["filename"] for r in split}) != expected_count:
        raise ValueError(f"Split harus berisi {expected_count} nama unik; ditemukan {len(split)} baris.")
    manifest = {r["filename"]: r for r in csv.DictReader(manifest_path.open(encoding="utf-8-sig", newline=""))}
    packaged = []
    for row in split:
        filename, condition = row["filename"], row["category"]
        entry = manifest.get(filename)
        if not entry or entry["condition"] != condition:
            raise ValueError(f"Foto tidak ada/condition tidak cocok di manifest: {filename} ({condition})")
        rel = f"dataset/raw_photos/{condition}/{filename}"
        path = root / condition / filename
        if not path.is_file():
            raise FileNotFoundError(f"Foto split tidak ditemukan: {path}")
        data = path.read_bytes()
        if len(data) != int(entry["size_bytes"]):
            raise ValueError(f"Ukuran foto tidak cocok dengan photo_manifest.csv: {filename}")
        if hashlib.sha256(data).hexdigest().casefold() != entry["sha256"].casefold():
            raise ValueError(f"SHA-256 foto tidak cocok dengan photo_manifest.csv: {filename}")
        packaged.append((rel, data))
    return packaged


def build_bundle(output: Path = OUTPUT, tag: str = TAG, config_name: str = CONFIG_NAME) -> dict:
    result = subprocess.run(["git", "archive", "--format=tar", tag], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"git archive {tag} gagal: {result.stderr.decode(errors='replace').strip()}")
    archive_bytes = io.BytesIO(result.stdout)
    output.parent.mkdir(parents=True, exist_ok=True)
    tracked_count = 0
    tracked_files: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=archive_bytes, mode="r:") as source:
        for member in source.getmembers():
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Path tidak aman pada git archive: {member.name}")
            data_file = source.extractfile(member)
            if data_file is None:
                continue
            tracked_files.append((path.as_posix(), data_file.read()))
            tracked_count += 1
    tracked = dict(tracked_files)
    sidecar_name = config_name.replace(".json", ".sha256")
    config_data = tracked.get(f"evaluation/{config_name}")
    config_hash_data = tracked.get(f"evaluation/{sidecar_name}")
    if not config_data or not config_hash_data:
        raise RuntimeError(f"Tag harus memuat evaluation/{config_name} dan evaluation/{sidecar_name}.")
    config = json.loads(config_data.decode("utf-8-sig"))
    if config.get("status") != "frozen":
        raise RuntimeError(f"Tag {tag} config berstatus {config.get('status')!r}; bundle ditolak.")
    expected_config_hash = config_hash_data.decode("ascii").strip().split()[0]
    if hashlib.sha256(config_data).hexdigest().casefold() != expected_config_hash.casefold():
        raise RuntimeError("SHA-256 config dalam tag tidak cocok dengan sidecar.")
    split_data, manifest_data = tracked.get("evaluation/splits/evaluation_set.csv"), tracked.get("dataset/photo_manifest.csv")
    if not split_data or not manifest_data:
        raise RuntimeError("Tag tidak memuat split evaluasi atau photo_manifest.csv.")
    with tempfile.TemporaryDirectory() as temp_dir:
        split_path = Path(temp_dir) / "evaluation_set.csv"
        manifest_path = Path(temp_dir) / "photo_manifest.csv"
        split_path.write_bytes(split_data)
        manifest_path.write_bytes(manifest_data)
        photo_files = verified_photo_bytes(PHOTOS, split_path, manifest_path)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for rel, data in tracked_files:
            bundle.writestr(rel, data)
        for rel, data in photo_files:
            bundle.writestr(rel, data)
    return {"output": str(output), "tag": tag, "tracked_files": tracked_count,
            "verified_photos": len(photo_files), "zip_bytes": output.stat().st_size,
            "zip_test": zipfile.ZipFile(output).testzip()}


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        photo_root = root / "photos"
        (photo_root / "datar").mkdir(parents=True)
        data = b"fixture-photo-bytes"
        photo = photo_root / "datar" / "fixture.jpeg"
        photo.write_bytes(data)
        manifest = root / "manifest.csv"
        manifest.write_text("filename,condition,size_bytes,sha256\nfixture.jpeg,datar," + str(len(data)) + "," + hashlib.sha256(data).hexdigest() + "\n", encoding="utf-8")
        split = root / "split.csv"
        split.write_text("filename,category\nfixture.jpeg,datar\n", encoding="utf-8")
        assert verified_photo_bytes(photo_root, split, manifest, expected_count=1) == [("dataset/raw_photos/datar/fixture.jpeg", data)]
        manifest.write_text(manifest.read_text().replace(hashlib.sha256(data).hexdigest(), "0" * 64), encoding="utf-8")
        try:
            verified_photo_bytes(photo_root, split, manifest, expected_count=1)
        except ValueError as exc:
            assert "SHA-256" in str(exc)
        else:
            raise AssertionError("Mismatch SHA harus ditolak")
    print("Bundle helper self-test: fixture SHA and paths valid.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=TAG)
    parser.add_argument("--config", default=CONFIG_NAME,
                        help="Nama berkas konfigurasi beku di dalam tag, mis. config_frozen_v2.json")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    print(build_bundle(args.output, args.tag, args.config))


if __name__ == "__main__":
    main()
