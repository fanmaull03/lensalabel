"""Count requested longest-match phrases in transcripts and saved OCR only."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS = ROOT / "dataset/ground_truth/transcripts.csv"
SAVED_OCR = ROOT / "evaluation/results/transcript_photo_audit/fresh_audit/raw_evidence_complete.json"
OUT = ROOT / "evaluation/results/kb_v2_phase2"
PHRASES = {
    "susu kedelai": ["susu kedelai", "soy milk"],
    "susu kelapa": ["susu kelapa", "coconut milk"],
    "susu beras": ["susu beras", "rice milk"],
    "susu almond": ["susu almond", "almond milk"],
    "cocoa butter": ["cocoa butter", "lemak kakao"],
    "peanut butter": ["peanut butter", "selai kacang tanah"],
    "krimer nabati": ["krimer nabati", "plant-based creamer"],
    "cream of tartar": ["cream of tartar", "krim tartar"],
}


def count_phrase(text: str, phrase: str) -> int:
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"(?!\w)"
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def main() -> None:
    with TRANSCRIPTS.open(encoding="utf-8-sig", newline="") as stream:
        transcripts = {row["filename"]: row["ground_truth_text"] for row in csv.DictReader(stream)}
    saved = json.loads(SAVED_OCR.read_text(encoding="utf-8"))
    if len(transcripts) != 200 or len(saved) != 200 or set(transcripts) != set(saved):
        raise ValueError("Audit membutuhkan 200 transkrip dan 200 rekaman OCR tersimpan")
    rows = []
    plant_milk_photos = set()
    for label, variants in PHRASES.items():
        transcript_hits = []
        ocr_hits = []
        exact_requested_hits = []
        for filename, transcript in transcripts.items():
            transcript_count = sum(count_phrase(transcript, variant) for variant in variants)
            if transcript_count:
                transcript_hits.append((filename, transcript_count))
                if label.startswith("susu "):
                    plant_milk_photos.add(filename)
            if count_phrase(transcript, label):
                exact_requested_hits.append(filename)
            ocr_text = saved[filename]["raw_ocr"]
            ocr_count = sum(count_phrase(ocr_text, variant) for variant in variants)
            if ocr_count:
                ocr_hits.append((filename, ocr_count))
        rows.append({"frasa": label, "varian_dihitung": " | ".join(variants),
                     "foto_transkrip": len(transcript_hits),
                     "kemunculan_transkrip": sum(count for _, count in transcript_hits),
                     "foto_frasa_persis_diminta": len(exact_requested_hits),
                     "foto_ocr_tersimpan_dengan_frasa": len(ocr_hits),
                     "kemunculan_ocr_tersimpan": sum(count for _, count in ocr_hits),
                     "filename_transkrip": " | ".join(name for name, _ in transcript_hits)})
    # Only a known plant-milk phrase in the transcript can validate that an
    # OCR typo fell back to generic "Susu". An unpaired OCR word is not proof.
    paired_potential = [filename for filename in plant_milk_photos
                        if count_phrase(saved[filename]["raw_ocr"], "susu")]
    summary = {"transcript_photos": len(transcripts), "saved_ocr_photos": len(saved),
               "plant_milk_gt_photos": len(plant_milk_photos),
               "paired_ocr_photos_with_susu": len(paired_potential),
               "confirmed_plant_milk_typo_fall_to_generic_susu": 0,
               "interpretation": "Tidak ada frasa susu nabati target pada transkrip 200 foto; tidak ada pasangan GT/OCR untuk mengukur salah-baca yang jatuh ke Susu."}
    with (OUT / "longest_match_frequency.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "longest_match_frequency_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
