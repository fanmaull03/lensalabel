"""Replay the same 40 cached OCR inputs with old/new GT and matchers."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]

from app.classifier.rule_based import classify_product
from app.matching.fuzzy_matcher import load_knowledge_base_from_json, match_token, match_token_many
from app.ocr.reader import sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section, tokenize
from evaluation.run_grid_search import THRESHOLDS, write_csv


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def metrics(tp, fp, fn):
    return dict(tp=tp, fp=fp, fn=fn,
                precision=tp / (tp + fp) if tp + fp else 0,
                recall=tp / (tp + fn) if tp + fn else 0,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-gt', required=True, type=Path)
    parser.add_argument('--new-gt', required=True, type=Path)
    parser.add_argument('--cache-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--split', type=Path, default=ROOT / 'evaluation/splits/calibration_set.csv')
    parser.add_argument('--kb', type=Path, default=ROOT / 'evaluation/kb_snapshot.json')
    parser.add_argument('--historical-detail', type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.split.open(encoding='utf-8-sig')))
    names = {r['filename'] for r in rows}
    if len(rows) != 40 or len(names) != 40:
        raise ValueError('Expected the unchanged 40-photo calibration split')
    old_gt, new_gt = read_json(args.old_gt), read_json(args.new_gt)
    if set(old_gt) != names or set(new_gt) != names:
        raise ValueError('Both ground truths must cover exactly the calibration split')
    kb = load_knowledge_base_from_json(args.kb)
    historical = {}
    if args.historical_detail:
        historical = {(r['filename'], int(r['threshold'])): r for r in
                      csv.DictReader(args.historical_detail.open(encoding='utf-8-sig'))}
        if len(historical) != 40 * len(THRESHOLDS):
            raise ValueError('Historical detail does not contain all 240 combinations')
    arms = {'a_old_gt_old_matcher': old_gt, 'b_new_gt_old_matcher': new_gt,
            'c_new_gt_new_matcher': new_gt, 'ablation_new_gt_many_only': new_gt}
    details, traces, timings = [], [], []
    totals = {(arm, t): [0, 0, 0] for arm in arms for t in THRESHOLDS}
    inputs = [args.old_gt, args.new_gt, args.split, args.kb,
              ROOT / 'backend/app/matching/fuzzy_matcher.py',
              ROOT / 'backend/app/ocr/reader.py', ROOT / 'backend/app/tokenizer/tokenizer.py']
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    for index, row in enumerate(rows, 1):
        filename = row['filename']
        path = args.cache_dir / f'{filename}.json'
        inputs.append(path)
        cache = read_json(path)
        if cache['filename'] != filename:
            raise ValueError(f'Wrong cache: {path}')
        ordered = sort_reading_order([(d['bbox'], d['text'], float(d['confidence']))
                                      for d in cache['detections']])
        raw = '\n'.join(text for _, text, _ in ordered)
        composition = extract_composition_section(raw)
        tokens = tokenize(composition)
        started = perf_counter()
        # Top-1 selection is independent of threshold; negation is still evaluated.
        old_matches = [match_token(t, kb, threshold=0) for t in tokens]
        timings.append(dict(filename=filename, matcher='old_top1_once', threshold=0,
                            seconds=perf_counter() - started))
        for threshold in THRESHOLDS:
            old_at_threshold = [replace(m, matched=False, ingredient_id=None,
                                        standard_name=None, category=None)
                                if m.score < threshold else m for m in old_matches]
            predictions = {'old': old_at_threshold}
            for label, shared in [('many', False), ('many_shared', True)]:
                started = perf_counter()
                predictions[label] = [m for t in tokens for m in match_token_many(
                    t, kb, threshold=threshold, shared_heads=shared)]
                timings.append(dict(filename=filename, matcher=label, threshold=threshold,
                                    seconds=perf_counter() - started))
            for arm, gt in arms.items():
                label = ('old' if arm in ('a_old_gt_old_matcher', 'b_new_gt_old_matcher')
                         else 'many_shared' if arm == 'c_new_gt_new_matcher' else 'many')
                matches = predictions[label]
                classified = classify_product(matches)
                predicted = {v['standard_name'] for c in ('aman', 'perhatian', 'hindari')
                             for v in classified[c]}
                expected = {v['standard_name'] for v in gt[filename]['ingredients']}
                tp, fp, fn = predicted & expected, predicted - expected, expected - predicted
                if arm == 'a_old_gt_old_matcher' and historical:
                    previous = historical[(filename, threshold)]
                    assert predicted == set(json.loads(previous['predicted'])), (filename, threshold, 'prediction drift')
                    assert expected == set(json.loads(previous['ground_truth'])), (filename, threshold, 'GT drift')
                counts = metrics(len(tp), len(fp), len(fn))
                for i, key in enumerate(('tp', 'fp', 'fn')):
                    totals[arm, threshold][i] += counts[key]
                details.append(dict(arm=arm, filename=filename, category=row['category'],
                                    threshold=threshold, **counts, verdict=classified['verdict'],
                                    ground_truth=json.dumps(sorted(expected), ensure_ascii=False),
                                    predicted=json.dumps(sorted(predicted), ensure_ascii=False),
                                    true_positive=json.dumps(sorted(tp), ensure_ascii=False),
                                    false_positive=json.dumps(sorted(fp), ensure_ascii=False),
                                    false_negative=json.dumps(sorted(fn), ensure_ascii=False)))
            traces.append(dict(filename=filename, threshold=threshold, composition=composition,
                               matches={k: [asdict(m) for m in v] for k, v in predictions.items()}))
        print(f'[{index}/40] {filename}', flush=True)
        # Preserve completed evidence if a notebook runtime is interrupted.
        write_csv(args.output_dir / 'comparison_detail.csv', details, list(details[0]))
    summary = [dict(arm=arm, threshold=t, n_photos=40, **metrics(*totals[arm, t]))
               for arm in arms for t in THRESHOLDS]
    write_csv(args.output_dir / 'comparison_summary.csv', summary, list(summary[0]))
    write_csv(args.output_dir / 'matcher_timing.csv', timings, list(timings[0]))
    (args.output_dir / 'match_traces.json').write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = dict(complete=True, python=platform.python_version(), platform=platform.platform(),
                    photos=40, thresholds=THRESHOLDS, historical_predictions_verified=len(historical),
                    timing_note='Old matcher scored once per token. Many matcher uses bounded LRU score cache; timings are execution logs, not a cold-cache speed benchmark.',
                    sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    if any(manifest['sha256'][p] != digest for p, digest in source_hashes.items()):
        raise RuntimeError('Source or GT changed during execution; rerun with fixed inputs')
    (args.output_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    by_key = {(r['arm'], r['filename'], r['threshold']): r for r in details}
    deltas = []
    for r in details:
        if r['arm'] != 'c_new_gt_new_matcher':
            continue
        old = by_key['b_new_gt_old_matcher', r['filename'], r['threshold']]
        for change, field in [('new_false_positive', 'false_positive'), ('recovered_false_negative', 'true_positive')]:
            for ingredient in sorted(set(json.loads(r[field])) - set(json.loads(old[field]))):
                evidence = next(t for t in traces if t['filename'] == r['filename'] and t['threshold'] == r['threshold'])
                matching = [m for m in evidence['matches']['many_shared'] if m['standard_name'] == ingredient and m['matched']]
                deltas.append(dict(filename=r['filename'], threshold=r['threshold'], change=change,
                                   standard_name=ingredient, matches=json.dumps(matching, ensure_ascii=False)))
    write_csv(args.output_dir / 'prediction_changes.csv', deltas,
              ['filename', 'threshold', 'change', 'standard_name', 'matches'])
    report = ['# Perbandingan GT dan matcher\n',
              'Replay cache OCR mentah yang sama, split 40 dan KB tetap. Tidak menjalankan OCR.\n',
              '| Kondisi | Threshold | TP | FP | FN | Precision | Recall | F1 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        report.append(f"| {r['arm']} | {r['threshold']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} |")
    report.extend(['', 'Selisih a→b mengukur koreksi GT; b→c mengukur matcher pada GT identik.',
                   'Ablation memisahkan multi-match dari penambahan kepala bersama.',
                   'Tidak memilih atau mengubah threshold produksi otomatis. Periksa FP baru di prediction_changes.csv.',
                   'Runtime dan hash input ada di run_manifest.json.'])
    (args.output_dir / 'comparison_report.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(json.dumps([r for r in summary if r['threshold'] == 70], indent=2), flush=True)


if __name__ == '__main__':
    main()
