"""Compare every transcript with raw OCR, preserving candidate cross-photo maps."""
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.ocr.reader import sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section

OUT = ROOT / "evaluation/results/transcript_photo_audit/fresh_audit"
STOP = set("komposisi ingredients ingredient mengandung dan dengan dari yang untuk dalam pada atau serta persen perisa pewarna pengawet pengatur keasaman alami sintetik buatan penstabil pengemulsi pemanis bubuk nabati rasa asam vitamin no ci ins bpom".split())


def word_set(text):
    return set(re.findall(r"[a-z]+", text.lower())) - STOP


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    transcripts = csv_rows(ROOT / "dataset/ground_truth/transcripts.csv")
    expected_eval = {r["filename"] for r in csv_rows(ROOT / "evaluation/splits/evaluation_set.csv")}
    expected_calibration = {r["filename"] for r in csv_rows(ROOT / "evaluation/splits/calibration_set.csv")}
    assert len(expected_eval) == 160 and len(expected_calibration) == 40
    assert not expected_eval & expected_calibration
    sets = {r["filename"]: word_set(r["ground_truth_text"]) for r in transcripts}
    counts = Counter(w for s in sets.values() for w in s)
    weights = {w: math.log(201 / (count + 1)) + 1 for w, count in counts.items()}
    photos, missing = {}, []
    for row in transcripts:
        name = row["filename"]
        cache = (ROOT / "evaluation/results/transcript_photo_audit/fresh_evaluation_ocr" if name in expected_eval else ROOT / "evaluation/results/colab_v4/ocr_cache") / (name + ".json")
        if not cache.exists():
            missing.append(name)
            continue
        payload = json.loads(cache.read_text(encoding="utf-8"))
        assert payload["filename"] == name
        detections = payload["detections"]
        ordered = sort_reading_order([(d["bbox"], d["text"], float(d["confidence"])) for d in detections])
        raw = "\n".join(text for _, text, _ in ordered)
        photos[name] = {"filename": name, "category": payload["category"], "raw_ocr": raw,
                        "extracted_composition": extract_composition_section(raw), "words": word_set(raw),
                        "confidence": sum(d["confidence"] * len(d["text"]) for d in detections) / max(1, sum(len(d["text"]) for d in detections)),
                        "detections": len(detections), "cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
                        "source": "FRESH_LOCAL_RAW_EVALUATION" if name in expected_eval else "COLAB_RAW_CALIBRATION"}
    if missing and not args.allow_partial:
        raise SystemExit(f"Missing {len(missing)} fresh caches; refusing final audit")
    OUT.mkdir(parents=True, exist_ok=True)
    def coverage(target, observed, fuzzy=False, joined=False):
        hits = {w for w in target if w in observed or (fuzzy and len(w) >= 5 and any(abs(len(w) - len(o)) <= 2 and ratio(w, o) >= 85 for o in observed)) or (joined and len(w) >= 5 and any(w in o for o in observed))}
        total = sum(weights[w] for w in target)
        return (sum(weights[w] for w in hits) / total if total else 0), hits
    manual_path = OUT / "manual_findings.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    by_name = {r["filename"]: r["ground_truth_text"] for r in transcripts}
    rows, rankings = [], []
    for name, photo in photos.items():
        exact, _ = coverage(sets[name], photo["words"])
        tolerant, hits = coverage(sets[name], photo["words"], fuzzy=True)
        joined, _ = coverage(sets[name], photo["words"], fuzzy=True, joined=True)
        others = sorted(((coverage(target, photo["words"])[0], other) for other, target in sets.items() if other != name), reverse=True)
        best, other = others[0]
        candidate = best >= .65 and best - exact >= .2 and len(sets[other]) >= 5
        status = "REVIEW_CROSS_PHOTO" if candidate else "REVIEW_LOW_OVERLAP" if tolerant < .45 else "NO_STRONG_AUTOMATIC_INDICATION"
        decision = manual.get(name, {})
        rows.append(dict(filename=name, category=photo["category"], source=photo["source"], status=decision.get("status", status),
                         automatic_status=status, exact_coverage=round(exact, 4), tolerant_coverage=round(tolerant, 4),
                         joined_word_diagnostic_coverage=round(joined, 4), confidence=round(photo["confidence"], 4),
                         best_other_transcript=other, best_other_exact_coverage=round(best, 4),
                         missing_words="; ".join(sorted(sets[name] - hits)), visual_note=decision.get("note", "NOT_VISUALLY_VERIFIED"),
                         ground_truth_text=by_name[name], raw_ocr=photo["raw_ocr"], extracted_composition=photo["extracted_composition"]))
        for rank, (score, other_name) in enumerate(others[:5], 1):
            rankings.append(dict(photo_filename=name, rank=rank, transcript_filename=other_name, exact_coverage=round(score, 4)))
    reverse = []
    for name, target in sets.items():
        ranked = sorted(((coverage(target, photo["words"])[0], other) for other, photo in photos.items()), reverse=True)
        for rank, (score, other) in enumerate(ranked[:5], 1):
            reverse.append(dict(transcript_filename=name, rank=rank, photo_filename=other, exact_coverage=round(score, 4)))
    rows.sort(key=lambda r: (r["status"] == "NO_STRONG_AUTOMATIC_INDICATION", r["tolerant_coverage"]))
    summary = dict(expected=200, processed=len(rows), fresh_evaluation=len(expected_eval & photos.keys()),
                   calibration=len(expected_calibration & photos.keys()), complete=not missing, missing=missing,
                   statuses=dict(Counter(r["status"] for r in rows)),
                   limitations="Automated raw-OCR screening is not visual proof. Confidence is not proof of correct OCR. Rankings identify candidates, not automatic assignments; short/subset transcripts may rank highly for unrelated photos. Joined-word coverage is a secondary diagnostic, not chemistry matching.")
    suffix = "partial" if missing else "complete"
    for filename, selected in [(f"audit_{suffix}.csv", rows), (f"photo_to_transcript_{suffix}.csv", rankings), (f"transcript_to_photo_{suffix}.csv", reverse)]:
        with (OUT / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
            writer.writeheader()
            writer.writerows(selected)
    wb = Workbook()
    wb.remove(wb.active)
    for title, selected in [("Raw_OCR_audit", rows), ("Photo_to_transcript", rankings), ("Transcript_to_photo", reverse)]:
        ws = wb.create_sheet(title)
        ws.append(list(selected[0]))
        for row in selected:
            ws.append(list(row.values()))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 30
    wb.save(OUT / f"audit_{suffix}.xlsx")
    (OUT / f"summary_{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    serial_photos = {name: {key: value for key, value in photo.items() if key != "words"} for name, photo in photos.items()}
    (OUT / f"raw_evidence_{suffix}.json").write_text(json.dumps(serial_photos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "missing"}, ensure_ascii=False, indent=2))
    for row in rows:
        if row["automatic_status"] != "NO_STRONG_AUTOMATIC_INDICATION":
            print(row["filename"], row["status"], row["tolerant_coverage"], row["best_other_transcript"], row["best_other_exact_coverage"])


if __name__ == "__main__":
    main()
