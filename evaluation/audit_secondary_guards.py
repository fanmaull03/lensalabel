"""Trace replay of secondary-only filters, plus 200-photo extraction regression."""
from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import itertools
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT)]
from app.matching.fuzzy_matcher import MatchResult
from app.matching.secondary_guards import coverage_evidence, filter_secondary_matches
from app.tokenizer.tokenizer import extract_composition_section
from evaluation.calibration_annotations import strict_ingredients, joined_spelling_review_rows
from evaluation.compare_gt_matchers import metrics
from evaluation.run_grid_search import write_csv, THRESHOLDS

OUT = ROOT/'evaluation/results/secondary_guard_audit'
PREVIOUS = ROOT/'evaluation/results/gt_matcher_revision/local_comparison'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def csvout(name, rows):
    if rows:
        write_csv(OUT/name, rows, list(rows[0]))


def groups(trace):
    # Recover source token occurrences from the saved flattened trace. An offset
    # overlap means a repeated identical token, since accepted spans are disjoint.
    chunks = []
    for item in trace['matches']['many_shared']:
        overlap = chunks and any(item['span_start'] < x['span_end'] and x['span_start'] < item['span_end']
                                for x in chunks[-1] if item['matched'] and x['matched'])
        if not chunks or chunks[-1][0]['token'] != item['token'] or overlap:
            chunks.append([])
        chunks[-1].append(item)
    tokens = []
    for fragment in re.finditer(r'[^,;]+', trace['composition']):
        token = re.sub(r'\s+', ' ', fragment[0]).strip()
        if len(token) >= 2:
            tokens.append((token, fragment.start() + len(fragment[0])-len(fragment[0].lstrip())))
    assert len(tokens) == len(chunks), (trace['filename'], len(tokens), len(chunks))
    for (token, start), chunk in zip(tokens, chunks):
        assert token == chunk[0]['token']
        yield start, [MatchResult(**m) for m in chunk]


def main():
    kb = load(ROOT/'evaluation/kb_snapshot.json')
    gt = load(ROOT/'dataset/ground_truth/calibration_ingredients_gt_final.json')
    transcripts = {r['filename']:r for r in csv.DictReader((ROOT/'dataset/ground_truth/transcripts.csv').open(encoding='utf-8-sig'))}
    raw = load(ROOT/'evaluation/results/transcript_photo_audit/fresh_audit/raw_evidence_complete.json')
    traces = load(PREVIOUS/'match_traces.json')
    baseline = {(r['filename'],int(r['threshold'])):r for r in csv.DictReader((PREVIOUS/'comparison_detail.csv').open(encoding='utf-8-sig')) if r['arm']=='b_new_gt_old_matcher'}
    deltas = list(csv.DictReader((PREVIOUS/'prediction_changes.csv').open(encoding='utf-8-sig')))
    by_delta = {(r['filename'],r['standard_name']):r['change'] for r in deltas if r['threshold']=='70'}
    occurrence_rows, case_rows = [], []
    configs = list(itertools.product((None,80,85,90),(False,True),(False,True)))
    totals, details = {}, []
    for trace in traces:
        name, threshold = trace['filename'],trace['threshold']
        expected = {v['standard_name'] for v in gt[name]['ingredients']}
        old = set(json.loads(baseline[name,threshold]['predicted']))
        unguarded = {m['standard_name'] for m in trace['matches']['many_shared'] if m['matched']}
        recovered = (unguarded & expected) - old
        added_fp = (unguarded-expected) - (old-expected)
        group_list = list(groups(trace))
        limited = extract_composition_section(raw[name]['raw_ocr'],close_secondary_panels=True)
        assert extract_composition_section(raw[name]['raw_ocr']) == trace['composition']
        cutoff = len(limited) if limited != trace['composition'] else None
        if cutoff is not None:
            assert trace['composition'].startswith(limited)
        if threshold == 70:
            for start, matches in group_list:
                rank = 0
                for m in matches:
                    if not m.matched:
                        continue
                    rank += 1
                    kind = by_delta.get((name,m.standard_name))
                    if not kind:
                        continue
                    context = m.token[max(0,m.span_start-90):min(len(m.token),m.span_end+90)]
                    evidence = coverage_evidence(m.matched_window,m.matched_variant)
                    # Conservative flag for review, NOT a manual noise label:
                    # interleaved OCR may place legitimate ingredients after it.
                    prefix = trace['composition'][:start+m.span_start]
                    panel_risk = bool(re.search(r'energi|energy|takaran|sajian|nutrition|gizi|persen|penyimpanan|simpan|konsumsi|fasilitas|kkal|\bAKG\b',prefix,re.I))
                    occurrence_rows.append(dict(filename=name,standard_name=m.standard_name,kind=kind,rank=rank,
                        score=m.score,window=m.matched_window,variant=m.matched_variant,context=context,
                        full_coverage=evidence['full_coverage'],generic_only=evidence['generic_only'],
                        coverage=evidence['coverage'],panel_context_risk=panel_risk,
                        supported_words=' | '.join(evidence['supported_words'])))
        for floor,b,c in configs:
            label=f'A{floor or "off"}_B{int(b)}_C{int(c)}'
            filtered=[]
            for start,matches in group_list:
                result=filter_secondary_matches(matches,minimum_score=floor,full_coverage=b,
                    end_offset=cutoff-start if c and cutoff is not None else None)
                original_first=next((m for m in matches if m.matched),None)
                if original_first:
                    assert next(m for m in result if m.matched)==original_first
                filtered.extend(result)
            predicted={m.standard_name for m in filtered if m.matched}
            assert predicted <= unguarded
            row=dict(config=label,threshold=threshold,filename=name,
                **metrics(len(predicted&expected),len(predicted-expected),len(expected-predicted)),
                fn_still_recovered=len(recovered&predicted),new_fp_removed=len(added_fp-predicted),
                recovered_lost=len(recovered-predicted),existing_tp_lost=len((old&expected)-predicted),
                predicted=json.dumps(sorted(predicted),ensure_ascii=False))
            details.append(row)
            key=label,threshold
            acc=totals.setdefault(key,{k:0 for k in ('tp','fp','fn','fn_still_recovered','new_fp_removed','recovered_lost','existing_tp_lost')})
            for k in acc: acc[k]+=row[k]
    summaries=[]
    for (label,t),counts in totals.items():
        summaries.append(dict(config=label,threshold=t,n_photos=40,**counts,
            **{k:v for k,v in metrics(counts['tp'],counts['fp'],counts['fn']).items() if k not in counts}))
    for key,kind in by_delta.items():
        matches=[r for r in occurrence_rows if (r['filename'],r['standard_name'])==key]
        assert matches and all(r['rank']>=2 for r in matches),key
        best=max(matches,key=lambda r:r['score'])
        case_rows.append(dict(best,occurrences=len(matches),any_full_coverage=any(r['full_coverage'] for r in matches)))
    distributions={}
    for kind in ('recovered_false_negative','new_false_positive'):
        cases=[r for r in case_rows if r['kind']==kind]
        scores=[r['score'] for r in cases]
        distributions[kind]=dict(cases=len(cases),score_min=min(scores),score_median=statistics.median(scores),score_max=max(scores),
            full_coverage=sum(r['full_coverage'] for r in cases),generic_only=sum(r['generic_only'] for r in cases),
            panel_context_risk=sum(r['panel_context_risk'] for r in cases),
            retained_by_score={str(t):sum(s>=t for s in scores) for t in (80,85,90)})
    csvout('ablation_summary.csv',summaries);csvout('ablation_detail.csv',details)
    csvout('secondary_occurrences.csv',occurrence_rows);csvout('secondary_cases.csv',case_rows)
    save('score_distributions.json',distributions)
    print('Ablations and distributions complete',distributions,flush=True)

    regression=[]
    for index,(name,entry) in enumerate(raw.items(),1):
        text=entry['raw_ocr']; before=extract_composition_section(text);after=extract_composition_section(text,close_secondary_panels=True)
        assert before==entry['extracted_composition'],name
        transcript=transcripts[name]['ground_truth_text']
        transcript_before=extract_composition_section(transcript);transcript_after=extract_composition_section(transcript,close_secondary_panels=True)
        lost=[];removed=''
        if before!=after:
            reference={x['standard_name'] for x in strict_ingredients(transcript_before,kb)}
            old_names={x['standard_name'] for x in strict_ingredients(before,kb)}
            new_names={x['standard_name'] for x in strict_ingredients(after,kb)}
            lost=sorted((old_names&reference)-new_names)
            removed=before[len(after):]
        regression.append(dict(filename=name,changed=before!=after,transcript_changed=transcript_before!=transcript_after,
            before_chars=len(before),after_chars=len(after),potential_valid_ingredients_lost=json.dumps(lost,ensure_ascii=False),
            retained_text=after,removed_text=removed,transcript_before=transcript_before,transcript_after=transcript_after))
        if index%40==0:print(f'Extraction regression {index}/200',flush=True)
    csvout('extraction_regression_200.csv',regression)
    candidates=[]
    for name,entry in gt.items():
        candidates.extend(joined_spelling_review_rows(name,entry['composition_text'],entry['ingredients'],kb))
    save('new_joined_candidates.json',candidates)
    import openpyxl
    wb=openpyxl.Workbook();ws=wb.active;ws.title='kandidat_baru'
    fields=['filename','standard_name','category','sumber','matched_variant','matched_text','potongan_teks','keputusan']
    ws.append(fields)
    for r in candidates:ws.append([r[k] for k in fields])
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    from openpyxl.worksheet.datavalidation import DataValidation
    validation=DataValidation(type='list',formula1='"Y,N"',allow_blank=True);ws.add_data_validation(validation)
    if candidates:validation.add(f'H2:H{len(candidates)+1}')
    for col in 'ABCDEFGH':ws.column_dimensions[col].width=28 if col!='G' else 90
    wb.save(OUT/'new_joined_candidates.xlsx')
    for filename,digest in load(OUT/'protected_hashes.json').items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest()==digest,filename
    save('completion.json',dict(complete=True,configs=len(configs),thresholds=list(THRESHOLDS),first_matches_unchanged=True,
        protected_files_unchanged=True,regression_photos=200,ocr_changed=sum(r['changed'] for r in regression),
        transcript_changed=sum(r['transcript_changed'] for r in regression),
        potential_loss_photos=sum(json.loads(r['potential_valid_ingredients_lost'])!=[] for r in regression),
        new_candidates=len(candidates)))
    print(load(OUT/'completion.json'),flush=True)


if __name__=='__main__':main()
