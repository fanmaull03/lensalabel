"""Screen all transcript/photo pairs using existing OCR evidence, without editing data."""
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation/results/transcript_photo_audit"
STOP = set("komposisi ingredients ingredient mengandung dan dengan dari yang untuk dalam pada atau serta persen perisa pewarna pengawet pengatur keasaman alami sintetik buatan penstabil pengemulsi pemanis bubuk nabati rasa asam vitamin no ci ins bpom".split())
VISUAL_FINDINGS = {
    "datar_047.jpeg": "Foto Simba Makura: cokelat pasta 47,27%, jagung, beras, terigu, kalsium karbonat. Transcript Mochaccino/lesitin kedelai/kopi berbeda; transcript datar_047 tampak sesuai foto datar_048.",
    "datar_048.jpeg": "Foto: lemak nabati, susu skim, whey, kopi 0,86%, Mochaccino/BHT. Transcript beras merah/kismis/chia berbeda; transcript datar_048 tampak sesuai foto datar_049.",
    "datar_049.jpeg": "Foto Nola: tepung beras merah 18%, tepung beras coklat 18%, kismis, chia. Transcript gandum utuh/mede/sorghum/telur berbeda. Transcript serupa juga tercatat pada datar_050; belum ditetapkan pemetaan pengganti.",
    "melengkung_049.jpeg": "Foto Teh Hitam/Apple: natrium sitrat/asam malat, perisa apel, steviol. Transcript Oolong/bikarbonat/ester sukrosa berbeda. Jangan hanya tukar dengan melengkung_050: persentase, asam malat dan flavor berbeda dari transcript itu.",
    "melengkung_050.jpeg": "Foto Pokka Oolong 0,9%: natrium bikarbonat, ester sukrosa asam lemak. Transcript teh hitam/apel/steviol berbeda. Transcript melengkung_049 sesuai jenis dan daftar bahan pada foto ini.",
}


def words(text):
    return set(re.findall(r"[a-z]+", text.lower())) - STOP


def main():
    def csv_rows(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    transcripts = csv_rows(ROOT / "dataset/ground_truth/transcripts.csv")
    regression = {r["filename"]: r for r in csv_rows(ROOT / "evaluation/results/full_reading_order_regression.csv")}
    evidence = json.loads((ROOT / "evaluation/results/colab_v4/fn_diagnostic/evidence.json").read_text(encoding="utf-8"))
    assert len(transcripts) == len(regression) == 200
    gt = {r["filename"]: words(r["ground_truth_text"]) for r in transcripts}
    document_frequency = Counter(w for value in gt.values() for w in value)
    weights = {w: math.log((201) / (count + 1)) + 1 for w, count in document_frequency.items()}
    def coverage(target, observed, fuzzy=False):
        hits = {w for w in target if w in observed or (fuzzy and len(w) >= 5 and any(abs(len(w) - len(o)) <= 2 and ratio(w, o) >= 85 for o in observed))}
        total = sum(weights[w] for w in target)
        return (sum(weights[w] for w in hits) / total if total else 0), hits
    rows = []
    for source in transcripts:
        filename = source["filename"]
        old = regression[filename]
        photo = evidence["photos"].get(filename)
        raw = photo["ocr_reading_order_text"] if photo else ""
        ocr = raw if photo else old["comp_v2"]
        observed = words(ocr)
        exact, exact_hits = coverage(gt[filename], observed)
        tolerant, hits = coverage(gt[filename], observed, True)
        old_before, _ = coverage(gt[filename], words(old["comp_v1"]), True)
        alternatives = sorted(((coverage(target, observed)[0], other) for other, target in gt.items() if other != filename), reverse=True)
        best_score, best_name = alternatives[0]
        status = "TIDAK_ADA_INDIKASI_KUAT"
        if filename in VISUAL_FINDINGS:
            status = "TERKONFIRMASI_TRANSCRIPT_BERBEDA"
        elif tolerant < .45:
            status = "CEK_MANUAL_OVERLAP_RENDAH"
        elif exact < .6 and best_score > exact + .2:
            status = "CEK_MANUAL_ALTERNATIF_LEBIH_COCOK"
        elif old_before > tolerant + .25:
            status = "CEK_EKSTRAKSI_READING_ORDER"
        cache_path = ROOT / "evaluation/results/colab_v4/ocr_cache" / (filename + ".json")
        confidence = None
        if cache_path.exists():
            detections = json.loads(cache_path.read_text(encoding="utf-8"))["detections"]
            confidence = sum(d["confidence"] * len(d["text"]) for d in detections) / max(1, sum(len(d["text"]) for d in detections))
        rows.append(dict(filename=filename, category=old["category"], status=status,
                         source="COLAB_RAW_OCR" if photo else "REGRESSION_EXTRACTED_OCR_NOT_RAW",
                         exact_weighted_coverage=round(exact, 4), typo_tolerant_weighted_coverage=round(tolerant, 4),
                         raw_ocr_confidence=round(confidence, 4) if confidence is not None else None,
                         old_before_coverage=round(old_before, 4), best_other_transcript=best_name,
                         best_other_exact_coverage=round(best_score, 4), missing_words="; ".join(sorted(gt[filename] - hits)),
                         visual_review=VISUAL_FINDINGS.get(filename, "BELUM_DIPUTUSKAN_MANUAL; overlap saja bukan bukti mismatch"),
                         ground_truth_text=source["ground_truth_text"], ocr_used=ocr,
                         old_comp_before=old["comp_v1"], old_comp_after=old["comp_v2"]))
    rows.sort(key=lambda r: (r["status"] == "TIDAK_ADA_INDIKASI_KUAT", r["typo_tolerant_weighted_coverage"]))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "audit_200.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    wb = Workbook()
    for ws, selected in [(wb.active, rows), (wb.create_sheet("Perlu_ditinjau"), [r for r in rows if r["status"] != "TIDAK_ADA_INDIKASI_KUAT"])]:
        ws.title = "Audit_200" if ws == wb.active else "Perlu_ditinjau"
        ws.append(list(rows[0]))
        for row in selected:
            ws.append(list(row.values()))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = 28
    wb.save(OUT / "audit_200.xlsx")
    summary = {"screened": len(rows), "raw_ocr_available": 40, "extracted_ocr_only": 160,
               "status_counts": dict(Counter(r["status"] for r in rows)),
               "method": "Unique alphabetic word recall weighted by IDF across 200 transcripts; stopwords removed; typo check ratio >=85 for words >=5. Cutoff .45 is a screening heuristic, not validated mismatch classifier. Alternative transcript comparison uses exact weighted coverage only, not identification proof.",
               "limitations": "160 photos use historical extracted OCR, not raw OCR, and lack confidence. Low overlap can be OCR/extraction failure; no indication does not establish transcript correctness. No transcript corrections were made.",
               "input_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT / "dataset/ground_truth/transcripts.csv", ROOT / "evaluation/results/full_reading_order_regression.csv"]}}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in rows:
        if row["status"] != "TIDAK_ADA_INDIKASI_KUAT":
            print(row["filename"], row["status"], row["typo_tolerant_weighted_coverage"], row["best_other_transcript"], row["best_other_exact_coverage"])


if __name__ == "__main__":
    main()
