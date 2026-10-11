import sys, re
from pathlib import Path
from rapidfuzz import fuzz
import cv2, easyocr

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REPO_ROOT = Path(r'd:\Kulyeah\SKRIPSI\project\lensalabel')
sys.path.insert(0, str(REPO_ROOT / 'backend'))

from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order
from app.tokenizer.tokenizer import (
    _find_marker,
    _find_closing_marker,
    OPEN_MARKERS,
    CLOSE_MARKERS,
    ALLERGEN_DISCLAIMER_MARKERS,
    WARNING_DISCLAIMER_MARKER,
    CLOSING_MARKER_THRESHOLD,
    extract_composition_section,
)

def sort_reading_order_v1(results: list):
    import numpy as np
    if not results: return []
    detections, heights = [], []
    for bbox, text, conf in results:
        xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
        detections.append((bbox, text, conf, sum(ys)/len(ys), min(xs)))
        heights.append(max(ys)-min(ys))
    tol = max(float(np.mean(heights))*0.5, 1.0)
    lines = []
    for det in sorted(detections, key=lambda x: x[3]):
        line = min(lines, key=lambda l: abs(l['center_y'] - det[3]), default=None)
        if line is None or abs(line['center_y'] - det[3]) > tol:
            lines.append({'center_y': det[3], 'items': [det]})
        else:
            line['items'].append(det)
            line['center_y'] = float(np.mean([item[3] for item in line['items']]))
    ordered = []
    for line in sorted(lines, key=lambda l: l['center_y']):
        ordered.extend(sorted(line['items'], key=lambda x: x[4]))
    return [(b, t, c) for b, t, c, _, _ in ordered]

reader = easyocr.Reader(['id', 'en'], gpu=False)

def inspect_photo(p_name):
    p_path = REPO_ROOT / 'dataset' / 'raw_photos' / 'datar' / p_name
    img = cv2.imread(str(p_path))
    prep = preprocess(img)
    ocr_img = _downscale(prep, MAX_OCR_WIDTH)
    raw = reader.readtext(ocr_img, detail=1)

    ord_v1 = sort_reading_order_v1(raw)
    txt_v1 = '\n'.join(t for _, t, _ in ord_v1)

    ord_v2 = sort_reading_order(raw, alpha=0.8)
    txt_v2 = '\n'.join(t for _, t, _ in ord_v2)

    print(f'==================================================')
    print(f'INVESTIGATION FOR {p_name}')
    print(f'==================================================')

    print('\n>>> V1 (BEFORE SORTING CHANGE) <<<')
    words_v1 = txt_v1.split()
    open_v1 = _find_marker(words_v1, OPEN_MARKERS)
    close_v1 = _find_closing_marker(words_v1, start=open_v1 + 1 if open_v1 is not None else 0)
    print(f'Open marker index: {open_v1} -> "{words_v1[open_v1] if open_v1 is not None else None}"')
    print(f'Close marker index: {close_v1} -> "{words_v1[close_v1] if close_v1 is not None else None}"')
    print('Extracted composition V1:')
    print(extract_composition_section(txt_v1))

    print('\n>>> V2 (AFTER SORTING CHANGE) <<<')
    words_v2 = txt_v2.split()
    open_v2 = _find_marker(words_v2, OPEN_MARKERS)
    close_v2 = _find_closing_marker(words_v2, start=open_v2 + 1 if open_v2 is not None else 0)
    print(f'Open marker index: {open_v2} -> "{words_v2[open_v2] if open_v2 is not None else None}"')
    print(f'Close marker index: {close_v2} -> "{words_v2[close_v2] if close_v2 is not None else None}"')
    print('Extracted composition V2:')
    print(extract_composition_section(txt_v2))

    print('\n>>> DETAILED CLOSING MARKER EVALUATION ON V2 WORDS <<<')
    start = open_v2 + 1 if open_v2 is not None else 0
    for i in range(start, len(words_v2)):
        context = ' '.join(words_v2[i : i + 20])
        normalized_context = re.sub(r'[^\w]+', ' ', context.upper()).strip()

        is_mengandung = normalized_context.startswith('MENGANDUNG ')
        if is_mengandung or 'ALERGEN' in normalized_context:
            print(f'\nAt word #{i} ("{words_v2[i]}"):')
            print(f'  Context snippet: "{context[:80]}..."')
            print(f'  Normalized context snippet: "{normalized_context[:80]}..."')
            print(f'  startswith("MENGANDUNG "): {is_mengandung}')
            for m in ALLERGEN_DISCLAIMER_MARKERS:
                print(f'    Contains "{m}": {m in normalized_context}')
            print(f'    Contains WARNING_DISCLAIMER_MARKER: {WARNING_DISCLAIMER_MARKER in normalized_context}')

        for marker in CLOSE_MARKERS:
            width = len(marker.split())
            window = ' '.join(words_v2[i : i + width])
            normalized_marker = re.sub(r'[^\w]+', ' ', marker.upper()).strip()
            normalized_window = re.sub(r'[^\w]+', ' ', window.upper()).strip()
            score = fuzz.ratio(normalized_marker, normalized_window)
            if score >= 60:
                print(f'  Marker check at #{i}: "{marker}" vs window "{normalized_window}" -> Score={score} (thresh={CLOSING_MARKER_THRESHOLD})')

if __name__ == '__main__':
    inspect_photo('datar_003.jpeg')
    print('\n\n')
    inspect_photo('datar_005.jpeg')
