from __future__ import annotations

"""Freeze the evaluation configuration after an explicit --confirm.

Dirty freeze inputs are committed first. If they are already committed and the
working tree is clean, the current HEAD is used as the input commit. The config
and hash sidecar are then committed, and eval-freeze-v1 points to that record.
An existing tag may be replaced only when it is an ancestor of HEAD and contains
an un-frozen draft config without a hash sidecar.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "evaluation/config_frozen.json"
CONFIG_SHA = ROOT / "evaluation/config_frozen.sha256"
HASH_MANIFEST = ROOT / "dataset/freeze_input_hashes.csv"
TAG = "eval-freeze-v1"
BASE_INPUT_PATHS = (
    "backend/app/matching/fuzzy_matcher.py",
    "backend/app/matching/pair_blocks.py",
    "backend/app/matching/chemical_pair_blocks.json",
    "backend/app/matching/secondary_guards.py",
    "backend/app/__init__.py",
    "backend/app/classifier/__init__.py",
    "backend/app/classifier/rule_based.py",
    "backend/app/db/__init__.py",
    "backend/app/db/models.py",
    "backend/app/matching/__init__.py",
    "backend/app/ocr/__init__.py",
    "backend/app/preprocessing/__init__.py",
    "backend/app/tokenizer/__init__.py",
    "backend/app/tokenizer/tokenizer.py",
    "backend/app/ocr/reader.py",
    "backend/app/preprocessing/pipeline.py",
    "evaluation/results/kb_v2_phase2/kb_v2_review.json",
    "dataset/ground_truth/calibration_ingredients_gt_final.json",
    "dataset/ground_truth/calibration_ingredients_gt_v2_2.json",
    "dataset/ground_truth/transcripts.csv",
    "dataset/photo_manifest.csv",
    "dataset/freeze_input_hashes.csv",
    "evaluation/splits/evaluation_set.csv",
    "evaluation/splits/calibration_set.csv",
    "backend/requirements.txt",
    "requirements-dev.txt",
    "evaluation/requirements-colab.txt",
    "evaluation/run_ocr_evaluation.py",
    "evaluation/colab_evaluate_160_ocr.py",
    "evaluation/evaluate_160_metrics.py",
    "evaluation/build_eval_gt_final.py",
    "evaluation/audit_review_decisions.py",
    "evaluation/run_calibration_grid_v2.py",
    "evaluation/rescore_calibration_grid_from_cached_matches.py",
    "evaluation/calibration_grid_v2_2_provenance.json",
    "evaluation/calibration_grid_v2_2_comparison.csv",
    "evaluation/calibration_grid_v2_2_summary.csv",
    "evaluation/recompute_ablation_metrics.py",
    "evaluation/make_chapter4_assets.py",
    "evaluation/make_calibration_gt_v2_2.py",
    "evaluation/build_colab_eval_bundle.py",
    "evaluation/COLAB_EVAL_RUNBOOK.md",
    "evaluation/freeze_evaluation_config.py",
    "evaluation/tests/test_metric_levels.py",
    "docs/evaluation/verdict_metrics.md",
    "evaluation/tests/test_r1_span_resolution.py",
    "evaluation/tests/test_colab_eval_integrity.py",
    "evaluation/frozen_config.py",
    "backend/app/db/knowledge_base_gfcf.json",
)
CONFIG_PATH = "evaluation/config_frozen.json"


def commit_input_paths() -> tuple[str, ...]:
    optional_gt = "evaluation/ground_truth/evaluation_gt_final.json"
    paths = (*BASE_INPUT_PATHS,
             *((optional_gt,) if (ROOT / optional_gt).is_file() else ()))
    return tuple(dict.fromkeys(paths))


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def validated_draft_tag(head: str) -> str | None:
    """Return the stale draft tag's commit, or reject unsafe tag replacement."""
    if not git("tag", "--list", TAG):
        return None
    tagged_commit = git("rev-parse", "--verify", f"{TAG}^{{commit}}")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", tagged_commit, head], cwd=ROOT)
    if ancestor.returncode != 0:
        raise SystemExit(f"Tag {TAG} bukan leluhur HEAD; tag tidak akan dipindahkan.")
    config_result = subprocess.run(["git", "show", f"{TAG}:evaluation/config_frozen.json"], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if config_result.returncode != 0:
        raise SystemExit(f"Tag {TAG} tidak memiliki evaluation/config_frozen.json; tag tidak aman untuk diganti.")
    tagged_config = json.loads(config_result.stdout)
    if tagged_config.get("status") != "draft":
        raise SystemExit(f"Tag {TAG} sudah memuat config berstatus {tagged_config.get('status')!r}; tag tidak akan dipindahkan.")
    sidecar = subprocess.run(["git", "cat-file", "-e", f"{TAG}:evaluation/config_frozen.sha256"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sidecar.returncode == 0:
        raise SystemExit(f"Tag {TAG} sudah memuat config_frozen.sha256; tag tidak akan dipindahkan.")
    return tagged_commit


def distribution_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return None


def environment_versions() -> dict:
    versions = {
        "python": sys.version.split()[0],
        "easyocr": distribution_version("easyocr"),
        "torch": distribution_version("torch"),
        "opencv_python_headless": distribution_version("opencv-python-headless"),
        "opencv_python": distribution_version("opencv-python"),
        "opencv_contrib_python": distribution_version("opencv-contrib-python"),
    }
    try:
        import cv2
        versions["opencv_runtime"] = cv2.__version__
        versions["opencv_module_path"] = cv2.__file__
    except ImportError:
        versions["opencv_runtime"] = None
        versions["opencv_module_path"] = None
    installed_opencv = [key for key in ("opencv_python_headless", "opencv_python", "opencv_contrib_python")
                        if versions[key] is not None]
    if len(installed_opencv) != 1:
        raise RuntimeError(f"Harus tepat satu distribusi OpenCV; ditemukan {installed_opencv}.")
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="Commit input beku, set status frozen, dan buat tag eval-freeze-v1.")
    args = parser.parse_args()

    inputs = commit_input_paths()
    commit_paths = {*inputs, CONFIG_PATH}
    missing = [path for path in (*inputs, CONFIG_PATH)
               if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit("File freeze belum lengkap: " + ", ".join(missing))
    if git("rev-parse", "--verify", "HEAD", check=False) == "":
        raise SystemExit("Git HEAD tidak tersedia.")
    head = git("rev-parse", "HEAD")
    stale_tag_commit = validated_draft_tag(head)
    if CONFIG_SHA.exists():
        raise SystemExit(f"{CONFIG_SHA.relative_to(ROOT)} sudah ada sementara config belum dibekukan; periksa manual, tidak akan ditimpa.")

    # Never absorb an unrelated staged change into the freeze commit.
    staged = git("diff", "--cached", "--name-only")
    if staged:
        raise SystemExit("Index Git harus kosong sebelum freeze. File staged: " + staged.replace("\n", ", "))

    status_lines = git("status", "--porcelain", "--untracked-files=all").splitlines()
    relevant_dirty = []
    unrelated_dirty = []
    for line in status_lines:
        path = line[3:].strip().strip('"')
        (relevant_dirty if path in commit_paths else unrelated_dirty).append(path)
    print(json.dumps({
        "relevant_paths": list(inputs) + [CONFIG_PATH],
        "input_count": len(inputs) + 1,
        "relevant_dirty_paths": relevant_dirty,
        "unrelated_dirty_paths_ignored": len(unrelated_dirty),
        "tag": TAG,
        "existing_draft_tag_commit": stale_tag_commit,
        "existing_tag_will_be_replaced_only_after_successful_freeze": stale_tag_commit is not None,
        "confirm": args.confirm,
        "config_sha256_record": str(CONFIG_SHA.relative_to(ROOT)),
        "config_sha256_record_created_on_confirm": True,
        "config_sha256_record_location": str(CONFIG_SHA.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    if not args.confirm:
        print("Dry run: tidak ada file, commit, atau tag yang diubah. Jalankan dengan --confirm setelah meninjau daftar di atas.")
        return
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("status") != "draft":
        raise SystemExit(f"Status konfigurasi harus 'draft', ditemukan {config.get('status')!r}.")
    env = environment_versions()

    if relevant_dirty:
        git("add", "--", *inputs, CONFIG_PATH)
        staged_paths = set(git("diff", "--cached", "--name-only").splitlines())
        if not staged_paths or not staged_paths.issubset({*inputs, CONFIG_PATH}):
            raise SystemExit(f"Isi index tidak sesuai daftar freeze: {sorted(staged_paths)}")
        git("commit", "-m", "Catat input konfigurasi evaluasi")
    source_commit = git("rev-parse", "HEAD")

    config["status"] = "frozen"
    config["commit_hash"] = source_commit
    config["frozen_inputs_clean_at_creation"] = True
    freeze_record_paths = {CONFIG_PATH, str(HASH_MANIFEST.relative_to(ROOT)),
                           str(CONFIG_SHA.relative_to(ROOT))}
    unrelated_status = [line for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
                        if line[3:].strip().strip('"') not in freeze_record_paths]
    config["working_tree_clean_at_creation"] = not bool(unrelated_status)
    config["environment_versions"] = env
    config["transcripts_sha256"] = hashlib.sha256(
        (ROOT / "dataset/ground_truth/transcripts.csv").read_bytes()).hexdigest()
    config["frozen_at_utc"] = datetime.now(timezone.utc).isoformat()
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_digest = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    CONFIG_SHA.write_text(config_digest + "  config_frozen.json\n", encoding="ascii")
    manifest_rows = []
    with HASH_MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        manifest_rows = list(csv.DictReader(stream))
    config_row = {"path": CONFIG_PATH, "size_bytes": str(CONFIG.stat().st_size), "sha256": config_digest}
    manifest_rows = [row for row in manifest_rows if row.get("path") != CONFIG_PATH]
    manifest_rows.append(config_row)
    with HASH_MANIFEST.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("path", "size_bytes", "sha256"))
        writer.writeheader()
        writer.writerows(manifest_rows)
    git("add", "--", CONFIG_PATH)
    git("add", "--", str(CONFIG_SHA.relative_to(ROOT)))
    git("add", "--", str(HASH_MANIFEST.relative_to(ROOT)))
    git("commit", "-m", "Bekukan konfigurasi dan catat hash")
    tag_args = ["tag", "-a", TAG, "-m", f"Frozen evaluation configuration based on {source_commit}"]
    if stale_tag_commit is not None:
        tag_args.insert(1, "-f")
    git(*tag_args)
    print(json.dumps({"input_commit": source_commit, "freeze_record_commit": git("rev-parse", "HEAD"),
                      "config_sha256": config_digest, "config_sha256_path": str(CONFIG_SHA.relative_to(ROOT)),
                      "tag": TAG, "environment_versions": env}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
