"""Create evaluation annotation/review from transcripts plus frozen KB only.

This utility does not import production match_token, OCR, reading-order,
photos, classifier, or predictions. Exact and lenient annotation helpers are
shared with the calibration annotation workflow.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from app.tokenizer.tokenizer import extract_composition_section
from evaluation.calibration_annotations import (
    TAXONOMY_SOURCE, joined_spelling_review_rows, review_rows, strict_ingredients,
)

SPLIT=ROOT/'evaluation/splits/evaluation_set.csv'
TRANSCRIPTS=ROOT/'dataset/ground_truth/transcripts.csv'
KB_PATH=ROOT/'evaluation/kb_snapshot.json'
OUT=ROOT/'evaluation/ground_truth'
STRICT=OUT/'evaluation_gt_strict.json'
REVIEW=OUT/'evaluation_review.xlsx'
SUMMARY=OUT/'evaluation_annotation_summary.json'
FLAG='ambigu_taksonomi_tunggu_ahli_gizi'


def readcsv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def regenerate(split, transcripts, kb):
    names=[r['filename'] for r in split]
    if len(names)!=160 or len(set(names))!=160:raise ValueError(f'Expected 160 unique evaluation photos, got {len(names)}')
    byname={r['filename']:r for r in transcripts}
    if len(byname)!=200 or any(n not in byname for n in names):raise ValueError('Transcript mapping must contain all 160 evaluation rows')
    if not kb:raise ValueError('Frozen KB is empty')
    strict={}; candidates=[]
    for srow in split:
        filename=srow['filename'];transcript=byname[filename]
        if transcript['category']!=srow['category']:raise ValueError(f'Category mismatch for {filename}')
        text=transcript['ground_truth_text']
        if not text.strip():raise ValueError(f'Empty transcript for {filename}')
        composition=extract_composition_section(text)
        ingredients=strict_ingredients(composition,kb)
        strict[filename]=dict(filename=filename,category=srow['category'],ground_truth_text=text,
                              composition_text=composition,ingredients=ingredients)
        ordinary=review_rows(filename,composition,ingredients,kb)
        joined=joined_spelling_review_rows(filename,composition,ingredients,kb)
        taxonomy_ids={r['ingredient_id'] for r in ordinary if r['sumber']==TAXONOMY_SOURCE}
        rows={r['ingredient_id']:r for r in ordinary}
        for row in joined:
            if row['ingredient_id'] in rows:continue
            rows[row['ingredient_id']]=row
        for row in rows.values():
            ambiguous=row['sumber']==TAXONOMY_SOURCE or row['ingredient_id'] in taxonomy_ids
            row[FLAG]=FLAG if ambiguous else ''
            candidates.append(row)
    return strict,candidates


def make_workbook(candidates,summary):
    wb=openpyxl.Workbook();ws=wb.active;ws.title='kandidat_review'
    fields=['filename','standard_name','category','sumber','potongan_teks','keputusan',
            'matched_variant','matched_text',FLAG]
    ws.append(fields)
    for r in candidates:ws.append([r.get(k,'') for k in fields])
    validation=DataValidation(type='list',formula1='"Y,N"',allow_blank=True)
    validation.errorTitle='Keputusan tidak valid';validation.error='Isi Y untuk menerima, N untuk menolak, atau kosong untuk belum diputuskan.'
    validation.showErrorMessage=True;ws.add_data_validation(validation)
    if candidates:validation.add(f'F2:F{len(candidates)+1}')
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    widths={'A':24,'B':57,'C':16,'D':40,'E':100,'F':16,'G':52,'H':50,'I':45}
    for col,width in widths.items():ws.column_dimensions[col].width=width
    for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='24465A')
    for row in ws.iter_rows(min_row=2):
        for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    sm=wb.create_sheet('ringkasan');sm.append(['item','nilai'])
    for k,v in summary.items():sm.append([k,json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v])
    sm.freeze_panes='A2';sm.column_dimensions['A'].width=34;sm.column_dimensions['B'].width=90
    return wb


def main():
    split=readcsv(SPLIT);transcripts=readcsv(TRANSCRIPTS)
    kb=json.loads(KB_PATH.read_text(encoding='utf-8-sig'))
    strict,candidates=regenerate(split,transcripts,kb)
    if 'datar_047.jpeg' not in strict:raise AssertionError('datar_047 must be in evaluation GT')
    categories=Counter(x['category'] for v in strict.values() for x in v['ingredients'])
    sources=Counter(x['sumber'] for x in candidates)
    summary=dict(method='transcript_exact_word_boundary_then_lenient_review_only',n_photos=len(strict),
        strict_ingredient_total=sum(map(lambda x:len(x['ingredients']),strict.values())),
        strict_by_category=dict(categories),candidate_total=len(candidates),candidate_by_category=dict(Counter(x['category'] for x in candidates)),
        candidate_by_source=dict(sources),taxonomy_flag_total=sum(x[FLAG]==FLAG for x in candidates),
        joined_spelling_candidate_total=sum(x['sumber']=='ejaan_menyatu_terpisah_review' for x in candidates),
        decision_values=dict(Counter(x['keputusan'] or 'KOSONG' for x in candidates)),
        datar_047_in_evaluation=True,kb_sha256=hashlib.sha256(KB_PATH.read_bytes()).hexdigest(),
        transcript_sha256=hashlib.sha256(TRANSCRIPTS.read_bytes()).hexdigest(),
        split_sha256=hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        prohibited_inputs_called=['production match_token','OCR','photos','historical prediction/grid result'])
    OUT.mkdir(parents=True,exist_ok=True)
    if STRICT.exists() or REVIEW.exists() or SUMMARY.exists():raise FileExistsError('Evaluation annotation output already exists; refusing to overwrite')
    payload=json.dumps(strict,ensure_ascii=False,indent=2)+'\n'
    wb=make_workbook(candidates,summary)
    wb.save(REVIEW)
    STRICT.write_text(payload,encoding='utf-8')
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Examples:',json.dumps(candidates[:5],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
