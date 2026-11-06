"""Parallel, resumable evaluation wrapper for the frozen 160-photo OCR run.

This wrapper never runs OCR and never edits frozen inputs. It caches the exact
per-photo matcher/classifier outputs in JSONL, verifies them against the
sequential frozen path on all 40 calibration OCR texts, then calls the frozen
metric functions to aggregate results.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from evaluation import evaluate_160_metrics as frozen_metrics  # noqa: E402
from evaluation.frozen_config import load_config  # noqa: E402

DEFAULT_EVAL_OCR = ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv"
DEFAULT_CAL_OCR = ROOT / "evaluation/results/calibration_ocr_ablation/ocr_ablation_detail.csv"
CAL_CONFIG_KEY = "width_1500_adaptive_off"
CAL_SPLIT = ROOT / "evaluation/splits/calibration_set.csv"
EVAL_SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
CAL_CACHE = ROOT / "evaluation/results/evaluation_ocr/calibration_equivalence_cache.jsonl"
EVAL_CACHE = ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"
CAL_REPORT = ROOT / "evaluation/results/evaluation_ocr/calibration_equivalence_report.json"

_WORKER: dict[str, Any] = {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_frozen_config(config: dict[str, Any], config_name: str | None = None) -> dict[str, str]:
    config_path = ROOT / "evaluation" / (config_name or "config_frozen.json")
    sidecar = config_path.with_name(config_path.name.replace(".json", ".sha256"))
    if not sidecar.is_file():
        raise RuntimeError(f"{sidecar.relative_to(ROOT)} tidak ditemukan")
    expected = sidecar.read_text(encoding="utf-8-sig").strip().split()[0]
    actual = sha256(config_path)
    if actual.casefold() != expected.casefold():
        raise RuntimeError(f"Hash {config_path.name} tidak cocok dengan sidecar")
    paths = {
        "config": config_path,
        "kb": ROOT / str(config["kb_path"]),
        "matcher": ROOT / "backend/app/matching/fuzzy_matcher.py",
        "pair_blocks_data": ROOT / "backend/app/matching/chemical_pair_blocks.json",
        "pair_blocks_code": ROOT / "backend/app/matching/pair_blocks.py",
        "secondary_guards": ROOT / "backend/app/matching/secondary_guards.py",
        "tokenizer": ROOT / "backend/app/tokenizer/tokenizer.py",
        "classifier": ROOT / "backend/app/classifier/rule_based.py",
        "metrics_code": ROOT / "evaluation/evaluate_160_metrics.py",
        "calibration_split": CAL_SPLIT,
        "evaluation_split": EVAL_SPLIT,
    }
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        if key == "kb" and sha256(path).casefold() != str(config["kb_sha256"]).casefold():
            raise RuntimeError("Hash KB tidak cocok dengan config frozen")
    for key, cfg_field in (("calibration_gt", "calibration_gt_path"),
                           ("evaluation_gt", "evaluation_gt_path")):
        path = ROOT / str(config[cfg_field])
        expected_hash = str(config[f"{key}_sha256"])
        if not path.is_file() or sha256(path).casefold() != expected_hash.casefold():
            raise RuntimeError(f"Hash {key} tidak cocok dengan config frozen")
        paths[key] = path
    result = {key: sha256(path) for key, path in paths.items()}
    result["config_sidecar"] = sha256(sidecar)
    return result


def flatten_kb(kb_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, int]]:
    used: set[int] = set()
    next_id = max((int(old) for e in kb_doc["ingredients"] for old in e.get("old_entry_ids", [])), default=0) + 1
    flat: list[dict[str, Any]] = []
    categories: dict[str, str] = {}
    ids: dict[str, int] = {}
    for entry in kb_doc["ingredients"]:
        ingredient_id = next((int(old) for old in entry.get("old_entry_ids", []) if int(old) not in used), None)
        if ingredient_id is None:
            while next_id in used:
                next_id += 1
            ingredient_id, next_id = next_id, next_id + 1
        used.add(ingredient_id)
        name = str(entry["standard_name"])
        categories[name] = str(entry["category"]).casefold()
        ids[name] = ingredient_id
        for variant in [name, *entry.get("synonyms", [])]:
            flat.append({"ingredient_id": ingredient_id, "standard_name": name,
                         "category": entry["category"], "name_variant": str(variant)})
    return flat, categories, ids


def validate_pair_blocks(config: dict[str, Any]) -> None:
    from app.matching.pair_blocks import pair_data
    data = pair_data()
    active = data["active_pairs"] + data.get("expert_distinct_pairs", [])
    if config.get("blocked_pairs") != active:
        raise RuntimeError("Blocked pairs runtime berbeda dari config frozen")


def _serialize_prediction(matches: list[Any], classification: dict[str, Any], ids: dict[str, int]) -> dict[str, Any]:
    spans = []
    for match in matches:
        item = asdict(match)
        if item.get("ingredient_id") is None and item.get("standard_name"):
            item["ingredient_id"] = ids.get(str(item["standard_name"]))
        spans.append(item)
    entries = []
    for category in ("aman", "perhatian", "hindari"):
        for item in classification[category]:
            entries.append({"ingredient_id": ids.get(item["standard_name"]),
                            "standard_name": item["standard_name"], "category": category,
                            "matched_window": item.get("matched_window"), "score": item.get("score")})
    entries.sort(key=lambda x: (x["category"], x["standard_name"], x["ingredient_id"] or -1))
    verdict = str(classification["verdict"])
    verdict_3class = "perhatian" if verdict in {"perlu_verifikasi", "tidak_terbaca"} else verdict
    return {"entries": entries, "matches": spans, "classification": classification,
            "verdict": verdict, "verdict_3class": verdict_3class}


def predict_sequential_reference(task: tuple[str, str, str], kb: list[dict[str, Any]],
                                 categories: dict[str, str], ids: dict[str, int],
                                 config: dict[str, Any]) -> dict[str, Any]:
    """Sequential implementation mirroring the frozen metrics loop."""
    from app.classifier.rule_based import classify_product
    from app.matching.fuzzy_matcher import match_token_many
    from app.tokenizer.tokenizer import extract_composition_section, tokenize
    filename, condition, raw = task
    tokens = tokenize(extract_composition_section(raw))
    matches = [match for token in tokens for match in match_token_many(
        token, kb, weights=config["weights"], threshold=float(config["threshold"]),
        shared_heads=True, length_penalty_exponent=float(config["length_penalty"]["exponent"]),
    )]
    classified = classify_product(matches)
    return {"record_type": "photo", "filename": filename, "condition": condition,
            "prediction": _serialize_prediction(matches, classified, ids)}


def init_worker(kb: list[dict[str, Any]], weights: dict[str, float], threshold: float,
                exponent: float, ids: dict[str, int]) -> None:
    """Load the frozen matcher in each process; only enlarge pure memoization."""
    import app.matching.fuzzy_matcher as matcher
    from functools import lru_cache
    matcher._bigrams = lru_cache(maxsize=100_000)(matcher._bigrams.__wrapped__ if hasattr(matcher._bigrams, "__wrapped__") else matcher._bigrams)
    matcher._many_score = lru_cache(maxsize=500_000)(matcher._many_score.__wrapped__ if hasattr(matcher._many_score, "__wrapped__") else matcher._many_score)
    matcher._best_fragment = lru_cache(maxsize=100_000)(matcher._best_fragment.__wrapped__ if hasattr(matcher._best_fragment, "__wrapped__") else matcher._best_fragment)
    _WORKER.update(kb=kb, weights=weights, threshold=threshold, exponent=exponent, ids=ids)


def worker_predict(task: tuple[str, str, str]) -> dict[str, Any]:
    from app.classifier.rule_based import classify_product
    from app.matching.fuzzy_matcher import match_token_many
    from app.tokenizer.tokenizer import extract_composition_section, tokenize
    filename, condition, raw = task
    tokens = tokenize(extract_composition_section(raw))
    matches = [match for token in tokens for match in match_token_many(
        token, _WORKER["kb"], weights=_WORKER["weights"], threshold=_WORKER["threshold"],
        shared_heads=True, length_penalty_exponent=_WORKER["exponent"],
    )]
    classified = classify_product(matches)
    return {"record_type": "photo", "filename": filename, "condition": condition,
            "prediction": _serialize_prediction(matches, classified, _WORKER["ids"])}


def cache_metadata(mode: str, provenance: dict[str, str], source_hash: str,
                   source_selector: str, config: dict[str, Any]) -> dict[str, Any]:
    return {"record_type": "metadata", "schema": 1, "mode": mode,
            "provenance": provenance, "source_sha256": source_hash,
            "source_selector": source_selector, "threshold": config["threshold"],
            "weights": config["weights"], "length_penalty": config["length_penalty"],
            "max_ocr_width": config["max_ocr_width"],
            "adaptive_threshold": config["adaptive_threshold"]}


def load_jsonl_cache(path: Path, expected_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    parsed: list[dict[str, Any]] = []
    valid_bytes = 0
    for index, line in enumerate(lines):
        if not line.endswith((b"\n", b"\r")) and index == len(lines) - 1:
            break  # recover a partial final append after an interrupted process
        try:
            parsed.append(json.loads(line.decode("utf-8")))
            valid_bytes += len(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JSONL cache rusak pada baris {index + 1}: {path}") from exc
    if not parsed or parsed[0] != expected_meta:
        raise RuntimeError(f"Provenance cache tidak cocok; pindahkan cache lama sebelum melanjutkan: {path}")
    if valid_bytes != len(raw):
        with path.open("r+b") as stream:
            stream.truncate(valid_bytes)
    records: dict[str, dict[str, Any]] = {}
    for row in parsed[1:]:
        if row.get("record_type") != "photo" or not row.get("filename"):
            raise RuntimeError(f"Baris cache bukan rekaman foto: {path}")
        filename = str(row["filename"])
        if filename in records:
            raise RuntimeError(f"Cache memuat foto duplikat: {filename}")
        records[filename] = row
    return records


def append_cache_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute_parallel(tasks: list[tuple[str, str, str]], cache_path: Path,
                     metadata: dict[str, Any], kb: list[dict[str, Any]],
                     weights: dict[str, float], threshold: float, exponent: float,
                     ids: dict[str, int], workers: int) -> dict[str, dict[str, Any]]:
    cached = load_jsonl_cache(cache_path, metadata)
    allowed = {task[0] for task in tasks}
    if not set(cached).issubset(allowed):
        raise RuntimeError("Cache berisi nama foto di luar split yang diminta")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        cache_path.write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    pending = [task for task in tasks if task[0] not in cached]
    print(f"Cache {cache_path.name}: {len(cached)}/{len(tasks)} selesai; proses tersisa {len(pending)}; workers={workers}", flush=True)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, initializer=init_worker,
            initargs=(kb, weights, threshold, exponent, ids),
        ) as pool:
            for done, row in enumerate(pool.map(worker_predict, pending, chunksize=1), start=1):
                append_cache_record(cache_path, row)
                cached[row["filename"]] = row
                print(f"[{len(tasks) - len(pending) + done}/{len(tasks)}] selesai {row['filename']}", flush=True)
    if set(cached) != allowed:
        raise RuntimeError("Cache belum lengkap untuk seluruh split")
    return {task[0]: cached[task[0]] for task in tasks}


def make_metric_records(split: list[dict[str, str]], predictions: dict[str, dict[str, Any]],
                        gt_doc: dict[str, Any], categories: dict[str, str],
                        transcripts: dict[str, str], ocr_by_name: dict[str, dict[str, str]] | None) -> list[dict[str, Any]]:
    from app.tokenizer.tokenizer import extract_composition_section
    rows = []
    for item in split:
        filename, condition = item["filename"], item["category"]
        result = predictions[filename]["prediction"]
        pred_names = {x["standard_name"] for x in result["entries"]}
        pred_categories = {categories.get(name, "aman") for name in pred_names}
        expected_items = gt_doc[filename].get("ingredients", [])
        gt_names = {str(x["standard_name"]) for x in expected_items}
        gt_category_by_name = {str(x["standard_name"]): str(x.get("category", "")).casefold()
                               for x in expected_items}
        category_map = {**categories, **gt_category_by_name}
        gt_categories = {gt_category_by_name.get(name, category_map.get(name, "aman")) for name in gt_names}
        system_status = result["verdict"]
        pred_verdict = result["verdict_3class"]
        counts = frozen_metrics.score_counts(gt_names, pred_names, category_map)
        row = {"filename": filename, "condition": condition,
               "ground_truth": sorted(gt_names), "predicted": sorted(pred_names),
               "gt_names": gt_names, "pred_names": pred_names,
               "_gt_categories": gt_categories, "_pred_categories": pred_categories,
               "gt_categories": sorted(gt_categories), "predicted_categories": sorted(pred_categories),
               "gt_verdict": frozen_metrics.strongest_category(gt_categories),
               "pred_verdict": pred_verdict, "system_status": system_status,
               "category_by_name": category_map,
               "tp": counts[0], "fp": counts[1], "fn": counts[2],
               "precision": counts[3], "recall": counts[4], "f1": counts[5],
               "ocr_runtime_seconds": float(ocr_by_name[filename]["ocr_runtime_seconds"]) if ocr_by_name else 0.0}
        for category in ("aman", "perhatian", "hindari"):
            values = frozen_metrics.score_counts(gt_names, pred_names, category_map, category)
            row[f"{category}_tp"], row[f"{category}_fp"], row[f"{category}_fn"] = values[:3]
        if ocr_by_name:
            raw = ocr_by_name[filename]["ocr_text"]
            composition = extract_composition_section(raw)
            for version, target, local in (("teks_penuh", raw, False),
                                           ("komposisi", composition, False),
                                           ("lokal", raw, True)):
                cer, wer = frozen_metrics.text_errors(transcripts[filename], target, local=local)
                row[f"cer_{version}"] = cer
                row[f"wer_{version}"] = wer
        rows.append(row)
    return rows


def write_metrics(records: list[dict[str, Any]], out_dir: Path, mode: str) -> None:
    summary, confusion = frozen_metrics.bootstrap_summary(records, iterations=1000, seed=42)
    for scope, condition in (("Keseluruhan", None), ("Datar", "datar"), ("Melengkung", "melengkung")):
        items = [row for row in records if condition is None or row["condition"] == condition]
        if not items or "cer_lokal" not in items[0]:
            continue
        for metric in ("cer", "wer"):
            for version in ("teks_penuh", "komposisi", "lokal"):
                values = [float(row[f"{metric}_{version}"]) for row in items]
                rng = random.Random(42)
                boot = [sum(values[rng.randrange(len(values))] for _ in values) / len(values) for _ in range(1000)]
                summary.append({"level": metric.upper(), "cakupan": scope, "kategori": version,
                                "metrik": "mean", "nilai": sum(values) / len(values),
                                "ci95_bawah": frozen_metrics.percentile(boot, .025),
                                "ci95_atas": frozen_metrics.percentile(boot, .975),
                                "resampling": 1000, "seed": 42, "jumlah_foto": len(values)})
    ci_rows = [{key: value for key, value in row.items()
                if key in {"level", "cakupan", "kategori", "metrik", "nilai", "ci95_bawah", "ci95_atas", "resampling", "seed", "jumlah_foto"}}
               for row in summary]
    details = [{**row,
                "ground_truth": json.dumps(row["ground_truth"], ensure_ascii=False),
                "predicted": json.dumps(row["predicted"], ensure_ascii=False),
                "gt_names": json.dumps(sorted(row["gt_names"]), ensure_ascii=False),
                "pred_names": json.dumps(sorted(row["pred_names"]), ensure_ascii=False),
                "_gt_categories": json.dumps(sorted(row["_gt_categories"]), ensure_ascii=False),
                "_pred_categories": json.dumps(sorted(row["_pred_categories"]), ensure_ascii=False),
                "category_by_name": json.dumps(row["category_by_name"], ensure_ascii=False)}
               for row in records]
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_metrics.write_csv(out_dir / "evaluation_metrics_detail.csv", details)
    frozen_metrics.write_csv(out_dir / "evaluation_metrics_summary.csv", summary)
    frozen_metrics.write_csv(out_dir / "evaluation_metrics_bootstrap_ci.csv", ci_rows)
    frozen_metrics.write_csv(out_dir / "evaluation_verdict_confusion.csv", confusion)
    cross = []
    for scope in ("keseluruhan", "datar", "melengkung"):
        cross.extend(frozen_metrics.system_status_cross_tab(records, scope=scope))
    frozen_metrics.write_csv(out_dir / "evaluation_verdict_status_cross_tab.csv", cross)
    statuses = [{"status_sistem": status, "jumlah": sum(row["system_status"] == status for row in records)}
                for status in frozen_metrics.SYSTEM_STATUSES]
    frozen_metrics.write_csv(out_dir / "evaluation_system_status_counts.csv", statuses)
    method = {"mode": mode, "prediction_cache": "evaluation_predictions_cache.jsonl",
              "ingredient_level": "set standard_name per photo",
              "category_level": "set category per photo, names ignored",
              "product_verdict": "highest-risk GT category vs classifier status; uncertainty maps to perhatian in 3-class matrix",
              "bootstrap": {"unit": "photo", "iterations": 1000, "seed": 42, "confidence": .95}}
    (out_dir / "evaluation_metrics_method.json").write_text(json.dumps(method, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_and_tasks(mode: str, config: dict[str, Any], expected_hashes: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, str], Path, str, str]:
    if mode == "evaluation":
        split, source, selector = read_csv(EVAL_SPLIT), DEFAULT_EVAL_OCR, "all_rows"
        if sha256(source) != expected_hashes.get("ocr_source"):
            raise RuntimeError("Hash OCR CSV tidak cocok dengan provenance pemanggil")
        rows = read_csv(source)
        if len(rows) != 160 or len({r["filename"] for r in rows}) != 160:
            raise RuntimeError("OCR CSV harus memuat 160 foto unik")
        if {(r["filename"], r["category"]) for r in rows} != {(r["filename"], r["category"]) for r in split}:
            raise RuntimeError("Nama/kondisi OCR CSV berbeda dari split evaluasi")
        if any(int(r["max_ocr_width"]) != int(config["max_ocr_width"]) or
               str(r["adaptive_threshold"]).casefold() != str(config["adaptive_threshold"]).casefold() for r in rows):
            raise RuntimeError("Konfigurasi OCR CSV berbeda dari config frozen")
    else:
        split, source, selector = read_csv(CAL_SPLIT), DEFAULT_CAL_OCR, CAL_CONFIG_KEY
        if sha256(source) != expected_hashes.get("ocr_source"):
            raise RuntimeError("Hash ablation OCR tidak cocok dengan provenance pemanggil")
        rows = [r for r in read_csv(source) if r.get("config_key") == CAL_CONFIG_KEY]
        if len(rows) != 40 or len({r["filename"] for r in rows}) != 40:
            raise RuntimeError("Ablation OCR harus memuat tepat 40 baris 1500/OFF")
        if {(r["filename"], r["condition"]) for r in rows} != {(r["filename"], r["category"]) for r in split}:
            raise RuntimeError("Nama/kondisi OCR ablation berbeda dari split kalibrasi")
    by_name = {row["filename"]: row for row in rows}
    return split, {name: str(row["ocr_text"]) for name, row in by_name.items()}, source, selector, sha256(source)


def verify_calibration(config: dict[str, Any], provenance: dict[str, str], workers: int) -> None:
    start = time.perf_counter()
    split, texts, source, selector, source_hash = source_and_tasks("calibration", config, {"ocr_source": sha256(DEFAULT_CAL_OCR)})
    kb_doc = json.loads((ROOT / str(config["kb_path"])).read_text(encoding="utf-8-sig"))
    kb, categories, ids = flatten_kb(kb_doc)
    validate_pair_blocks(config)
    tasks = [(row["filename"], row["category"], texts[row["filename"]]) for row in split]
    reference: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(tasks, start=1):
        reference[task[0]] = predict_sequential_reference(task, kb, categories, ids, config)
        print(f"[referensi {index}/40] selesai {task[0]}", flush=True)
    meta = cache_metadata("calibration_equivalence", provenance, source_hash, selector, config)
    parallel = execute_parallel(tasks, CAL_CACHE, meta, kb,
                                {k: float(v) for k, v in config["weights"].items()},
                                float(config["threshold"]), float(config["length_penalty"]["exponent"]), ids, workers)
    differences = [name for name in reference
                   if json.dumps(reference[name], sort_keys=True, ensure_ascii=False) !=
                   json.dumps(parallel[name], sort_keys=True, ensure_ascii=False)]
    if differences:
        report = {"passed": False, "prediction_mismatches": len(differences),
                  "mismatch_filenames": differences, "frozen_input_hashes": provenance}
        CAL_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("Wrapper tidak identik dengan jalur referensi pada kalibrasi; evaluasi 160 dibatalkan")
    gt_path = ROOT / str(config["calibration_gt_path"])
    gt_doc = json.loads(gt_path.read_text(encoding="utf-8-sig"))
    cal_ocr_rows = [r for r in read_csv(source) if r.get("config_key") == selector]
    transcripts = {r["filename"]: r["ground_truth_text"] for r in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    ocr_map = {r["filename"]: {"ocr_text": r["ocr_text"], "ocr_runtime_seconds": r.get("ocr_runtime_seconds", "0")}
               for r in cal_ocr_rows}
    ref_records = make_metric_records(split, reference, gt_doc, categories, transcripts, ocr_map)
    par_records = make_metric_records(split, parallel, gt_doc, categories, transcripts, ocr_map)
    ref_metrics = frozen_metrics.bootstrap_summary(ref_records, iterations=1000, seed=42)
    par_metrics = frozen_metrics.bootstrap_summary(par_records, iterations=1000, seed=42)
    text_equal = all(all(ref[f"{metric}_{version}"] == par[f"{metric}_{version}"]
                         for metric in ("cer", "wer") for version in ("teks_penuh", "komposisi", "lokal"))
                     for ref, par in zip(ref_records, par_records))
    metrics_equal = ref_metrics == par_metrics and text_equal
    report = {"passed": metrics_equal, "split": "calibration_only", "photos": 40,
              "predictions_identical": True, "mismatched_photos": 0,
              "metrics_identical": metrics_equal, "metric_max_absolute_delta": 0.0 if metrics_equal else None,
              "threshold": config["threshold"], "ocr_selector": selector,
              "ocr_source_sha256": source_hash, "frozen_input_hashes": provenance,
              "elapsed_seconds": round(time.perf_counter() - start, 3),
              "note": "Tidak ada prediksi per foto diekspor ke laporan."}
    CAL_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not metrics_equal:
        raise RuntimeError("Prediksi sama tetapi metrik referensi dan wrapper berbeda; evaluasi 160 dibatalkan")
    print("Kesetaraan lulus: prediksi 40/40 identik; metrik identik (delta 0).", flush=True)


def run_evaluation(config: dict[str, Any], provenance: dict[str, str], workers: int) -> None:
    if not CAL_REPORT.is_file():
        raise RuntimeError("Gerbang kesetaraan kalibrasi belum lulus")
    report = json.loads(CAL_REPORT.read_text(encoding="utf-8-sig"))
    if not report.get("passed") or report.get("frozen_input_hashes") != provenance:
        raise RuntimeError("Laporan kesetaraan tidak lulus atau provenance frozen berubah")
    split, texts, source, selector, source_hash = source_and_tasks("evaluation", config,
                                                                   {"ocr_source": sha256(DEFAULT_EVAL_OCR)})
    kb_doc = json.loads((ROOT / str(config["kb_path"])).read_text(encoding="utf-8-sig"))
    kb, categories, ids = flatten_kb(kb_doc)
    validate_pair_blocks(config)
    tasks = [(row["filename"], row["category"], texts[row["filename"]]) for row in split]
    meta = cache_metadata("evaluation_160", provenance, source_hash, selector, config)
    predicted = execute_parallel(tasks, EVAL_CACHE, meta, kb,
                                 {k: float(v) for k, v in config["weights"].items()},
                                 float(config["threshold"]), float(config["length_penalty"]["exponent"]), ids, workers)
    gt_path = ROOT / str(config["evaluation_gt_path"])
    gt_doc = json.loads(gt_path.read_text(encoding="utf-8-sig"))
    transcripts = {r["filename"]: r["ground_truth_text"] for r in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    ocr_map = {r["filename"]: r for r in read_csv(source)}
    records = make_metric_records(split, predicted, gt_doc, categories, transcripts, ocr_map)
    write_metrics(records, ROOT / "evaluation/results/evaluation_ocr", "persisted_ocr_parallel_cache")
    print("Metrik selesai; OCR tidak dijalankan ulang dan prediksi per foto tidak dicetak.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify-calibration", "run-evaluation"))
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--config", default=None,
                        help="Nama berkas konfigurasi beku, mis. config_frozen_v2.json. Default: config_frozen.json.")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > (os.cpu_count() or 1):
        raise ValueError(f"--workers harus antara 1 dan {os.cpu_count() or 1}")
    config = load_config(require_frozen=True, config_name=args.config)
    provenance = verify_frozen_config(config, args.config)
    validate_pair_blocks(config)
    if args.mode == "verify-calibration":
        verify_calibration(config, provenance, args.workers)
    else:
        run_evaluation(config, provenance, args.workers)


if __name__ == "__main__":
    main()
