"""Bandingkan seluruh prediksi eksperimen matcher dengan cache tag evaluasi beku."""

from __future__ import annotations

from collections import Counter
from io import BytesIO
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation import benchmark_perf_matcher_200 as benchmark
from evaluation import run_evaluate_160_parallel as wrapper
from evaluation.frozen_config import load_config


def _frozen_matcher_from_tag(folder: Path):
    archive = subprocess.check_output([
        "git", "archive", "--format=tar", "eval-freeze-v1",
        "backend/app/matching/fuzzy_matcher.py",
    ], cwd=ROOT)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as stream:
        member = stream.extractfile("backend/app/matching/fuzzy_matcher.py")
        if member is None:
            raise RuntimeError("Matcher tidak ditemukan di tag beku")
        source = member.read()
    path = folder / "fuzzy_matcher_frozen.py"
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location("fuzzy_matcher_frozen", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, hashlib.sha256(source).hexdigest()


def _first_difference(expected: object, actual: object, path: str = "prediction") -> str | None:
    if type(expected) is not type(actual):
        return path
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            return path + ".keys"
        for key in expected:
            found = _first_difference(expected[key], actual[key], path + "." + key)
            if found:
                return found
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return path + ".length"
        for index, (left, right) in enumerate(zip(expected, actual)):
            found = _first_difference(left, right, path + f"[{index}]")
            if found:
                return found
    elif expected != actual:
        return path
    return None


def main() -> None:
    config = load_config(require_frozen=True)
    source = json.loads((ROOT / config["kb_path"]).read_text(encoding="utf-8-sig"))
    kb, _, ids = wrapper.flatten_kb(source)
    eval_rows = benchmark.read_csv(ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv")
    cal_rows = [row for row in benchmark.read_csv(
        ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv"
    ) if row["config_key"] == "width_1500_adaptive_off"]
    if len(eval_rows) != 160 or len(cal_rows) != 40:
        raise RuntimeError("Sumber OCR 160 + 40 tidak lengkap")
    tasks = [(r["filename"], r["category"], r["ocr_text"]) for r in eval_rows]
    tasks += [(r["filename"], r["condition"], r["ocr_text"]) for r in cal_rows]
    expected = benchmark.load_cache(ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl")
    expected.update(benchmark.load_cache(
        ROOT / "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl"
    ))
    if len(expected) != 200:
        raise RuntimeError("Cache prediksi beku bukan 200 foto")

    with tempfile.TemporaryDirectory(prefix="lensalabel_frozen_matcher_") as folder:
        frozen, frozen_hash = _frozen_matcher_from_tag(Path(folder))
        meta = json.loads((ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl")
                          .read_text(encoding="utf-8").splitlines()[0])
        if frozen_hash != meta["provenance"]["matcher"]:
            raise RuntimeError("Cache lama bukan dari matcher pada tag beku")
        from app.classifier.rule_based import classify_product
        from app.tokenizer.tokenizer import extract_composition_section, tokenize
        first = tasks[0]
        matches = [match for token in tokenize(extract_composition_section(first[2]))
                   for match in frozen.match_token_many(
                       token, kb, weights=config["weights"], threshold=config["threshold"],
                       shared_heads=True,
                       length_penalty_exponent=config["length_penalty"]["exponent"],
                   )]
        reference = wrapper._serialize_prediction(matches, classify_product(matches), ids)
        reference = json.loads(json.dumps(reference, ensure_ascii=False))
        if reference != expected[first[0]]:
            raise RuntimeError("Eksekusi matcher tag tidak cocok dengan cache prediksi beku")
        print("Matcher dari git archive tag cocok dengan cache prediksi beku.", flush=True)

    results = benchmark.run(
        tasks, kb, config["weights"], config["threshold"],
        config["length_penalty"]["exponent"], ids,
        min(4, os.cpu_count() or 1),
    )
    differences = []
    field_counts = Counter()
    core_equal = 0
    for row in results:
        filename = row["filename"]
        old, new = expected[filename], row["prediction"]
        if benchmark.core_signature(old) == benchmark.core_signature(new):
            core_equal += 1
        if old == new:
            continue
        for field in ("entries", "matches", "classification", "verdict", "verdict_3class"):
            if old.get(field) != new.get(field):
                field_counts[field] += 1
        location = _first_difference(old, new)
        differences.append({"filename": filename, "first_difference": location,
                            "frozen_value": _value_at(old, location),
                            "local_value": _value_at(new, location)})
    report = {
        "photos": len(results),
        "full_prediction_identical": len(results) - len(differences),
        "core_prediction_identical": core_equal,
        "different_fields": dict(field_counts),
        "frozen_matcher_sha256": frozen_hash,
        "local_matcher_sha256": benchmark.sha256(ROOT / "backend/app/matching/fuzzy_matcher.py"),
        "optimized_worker_seconds_sum": sum(r["matcher_and_classifier_seconds"] for r in results),
        "differences": differences,
    }
    out = ROOT / "evaluation/results/post_eval_supplement/perf_full_equivalence_200.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "differences"},
                     ensure_ascii=False), flush=True)
    print("Contoh selisih pertama:", json.dumps(differences[:5], ensure_ascii=False), flush=True)


def _value_at(data: object, location: str | None):
    if not location:
        return None
    import re
    cursor = data
    try:
        for key, index in re.findall(r"\.([^.[\]]+)|\[(\d+)\]", location):
            cursor = cursor[key] if key else cursor[int(index)]
        return cursor
    except (KeyError, IndexError, TypeError):
        return None


if __name__ == "__main__":
    main()
