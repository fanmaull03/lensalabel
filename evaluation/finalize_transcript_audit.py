"""Verify imported Colab OCR and assemble the report without changing annotations."""
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "evaluation/results/transcript_photo_audit"
OUT = BASE / "fresh_audit"
sys.path.insert(0, str(ROOT / "backend"))
from app.ocr.reader import sort_reading_order
from app.tokenizer.tokenizer import extract_composition_section

EXTRA = {
    "melengkung_015.jpeg": "Susu skim 3,1%, kopi instant 1%, alpukat 0,003%, tokoferol campuran pekat sesuai foto. Overlap rendah akibat OCR teks kecil/kontras rendah, bukan transcript susu/kurma 039.",
    "melengkung_018.jpeg": "Kakao 1,6%, krimer protein susu, whey, glikosida steviol, penstabil fosfat dan perisa alami susu sesuai label foto sendiri.",
    "melengkung_096.jpeg": "Cincau 10,32%, daun cincau 0,5%, krisantemum, kalsium laktat, pandan, madu, licorice, karamel kelas I sesuai label.",
    "melengkung_076.jpeg": "Sirup frambozen: gula/sulfit, frambozen, asam sitrat, sukralosa dan karmoisin 14720 sesuai. Kemiripan dengan transcript sirup lain bukan salah pasang.",
    "melengkung_062.jpeg": "Kopi instan 1,4%, susu skim 1,0%, krimer, kakao, garam sesuai label sendiri; berbeda dari varian oat 064.",
    "melengkung_012.jpeg": "Greenfields leci: susu segar 51%, sari leci 0,1%, E466/E471/E331(iii)/E440/E415 dan dua kultur bakteri sesuai label sendiri.",
    "melengkung_064.jpeg": "Oat cappuccino: kopi 1,2%, krimer oat 1% (oat 13,5%), susu full cream 1,0%, penstabil fosfat sesuai. Ranking transcript 062 lebih tinggi karena sebagian kata spesifik tidak terbaca OCR.",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    summary = json.loads((OUT / "summary_complete.json").read_text(encoding="utf-8"))
    assert summary["complete"] and summary["processed"] == 200 and not summary["missing"]
    protected = json.loads((OUT / "protected_input_hashes.json").read_text(encoding="utf-8"))
    manifest = json.loads((BASE / "colab_bundle_manifest.json").read_text(encoding="utf-8"))["sha256"]
    for path, digest in {**protected, **manifest}.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, f"Input changed: {path}"
    splits = {label: {r["filename"]: r["category"] for r in read_csv(ROOT / f"evaluation/splits/{label}_set.csv")} for label in ("evaluation", "calibration")}
    assert len(splits["evaluation"]) == 160 and len(splits["calibration"]) == 40
    assert not splits["evaluation"].keys() & splits["calibration"].keys()
    evidence = json.loads((OUT / "raw_evidence_complete.json").read_text(encoding="utf-8"))
    assert set(evidence) == splits["evaluation"].keys() | splits["calibration"].keys()
    caches, detections = {}, 0
    for label, split in splits.items():
        folder = BASE / "fresh_evaluation_ocr" if label == "evaluation" else ROOT / "evaluation/results/colab_v4/ocr_cache"
        assert {p.name.removesuffix(".json") for p in folder.glob("*.json")} == set(split)
        for name, category in split.items():
            path = folder / (name + ".json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["filename"] == name and payload["category"] == category
            assert payload["detections"], name
            for item in payload["detections"]:
                assert 0 <= item["confidence"] <= 1
                assert len(item["bbox"]) == 4 and all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in item["bbox"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == evidence[name]["cache_sha256"], name
            ordered = sort_reading_order([(d["bbox"], d["text"], float(d["confidence"])) for d in payload["detections"]])
            raw = "\n".join(text for _, text, _ in ordered)
            assert raw == evidence[name]["raw_ocr"], name
            assert extract_composition_section(raw) == evidence[name]["extracted_composition"], name
            caches[name] = digest
            detections += len(payload["detections"])
    audit = read_csv(OUT / "audit_complete.csv")
    assert len(audit) == len({r["filename"] for r in audit}) == 200
    assert {r["filename"] for r in audit} == set(evidence)
    transcripts = {r["filename"]: r["ground_truth_text"] for r in read_csv(ROOT / "dataset/ground_truth/transcripts.csv")}
    for row in audit:
        name = row["filename"]
        assert row["ground_truth_text"] == transcripts[name]
        assert row["raw_ocr"] == evidence[name]["raw_ocr"]
        assert row["extracted_composition"] == evidence[name]["extracted_composition"]
    findings = json.loads((OUT / "manual_findings.json").read_text(encoding="utf-8"))
    for name, note in EXTRA.items():
        assert name not in findings
        findings[name] = {"status": "VISUAL_SELF_MATCH", "note": note}
    for row in audit:
        if row["filename"] in EXTRA:
            row["status"] = "VISUAL_SELF_MATCH"
            row["visual_note"] = EXTRA[row["filename"]]
    statuses = Counter(r["status"] for r in audit)
    automatic_flags = [r for r in audit if r["automatic_status"] != "NO_STRONG_AUTOMATIC_INDICATION"]
    assert all(r["filename"] in findings for r in automatic_flags)
    old = read_csv(BASE / "audit_200.csv")
    old_names = {r["filename"] for r in old if r["status"] != "TIDAK_ADA_INDIKASI_KUAT"}
    new_names = {r["filename"] for r in automatic_flags}
    runtime = json.loads((BASE / "colab_runtime.json").read_text())
    verification = dict(complete=True, fresh_evaluation_caches=160, calibration_caches=40, audited_photos=200,
                        missing=0, protected_inputs_verified=len(protected), bundle_inputs_verified=len(manifest),
                        reconstructed_raw_and_composition_verified=200, total_ocr_detections=detections,
                        visually_reviewed=len(findings), additional_visual_reviews=len(EXTRA), statuses=dict(statuses),
                        automatic_flags=len(automatic_flags), new_automatic_flags=sorted(new_names - old_names),
                        old_flags_no_longer_flagged=sorted(old_names - new_names), runtime=runtime, cache_sha256=caches)
    (OUT / "post_colab_verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "post_colab_visual_review.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "audit_final_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    wb = load_workbook(OUT / "cluster_review.xlsx")
    def sheet(title, rows):
        ws = wb.create_sheet(title)
        keys = list(rows[0])
        ws.append(keys)
        for row in rows:
            ws.append([row[k] for k in keys])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 28
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet("Audit_200_final", audit)
    sheet("Visual_32", [dict(filename=name, status=value["status"], bukti=value["note"]) for name, value in findings.items()])
    sheet("Ringkasan", [dict(pemeriksaan=k, hasil=str(v)) for k, v in verification.items() if k not in ("cache_sha256", "runtime", "statuses")])
    for direction in ("photo_to_transcript", "transcript_to_photo"):
        sheet(direction, read_csv(OUT / f"{direction}_complete.csv"))
    wb.save(OUT / "audit_final_review.xlsx")
    cluster = (OUT / "laporan_cluster_visual.md").read_text(encoding="utf-8")
    details = cluster[cluster.index("## Peta datar:"):cluster.index("## OCR segar dan sumber bukti")]
    lines = ["# Laporan audit transcript terhadap foto — hasil Colab lengkap", "", "Tanggal pemeriksaan: 6 Oktober 2026.", "",
             "## Hasil utama", "",
             "Audit OCR mentah seluruh **200 foto selesai**: 160 foto evaluasi diproses segar di Colab Tesla T4 dan digabung dengan 40 cache mentah kalibrasi. Semua cache lengkap, filename/category cocok split, hash cache sesuai bukti Colab, dan rekonstruksi lokal reading-order serta ekstraksi identik untuk 200 foto. Tidak ada fallback ke ekstraksi regresi historis.", "",
             "Penyaringan tidak menemukan kandidat salah pasang baru di luar lima kasus yang sudah diketahui. Peta cluster tetap datar transcript 047–049 dan melengkung transcript 049/050. **Ini hasil screening 200 + review visual terarah 32 foto, bukan sertifikasi visual seluruh 200.** Angka, typo kecil, atau produk sangat mirip masih bisa lolos overlap kata.", "",
             "| Hasil akhir | Foto |", "|---|---:|", "| Salah pasang dikonfirmasi visual | 5 |", "| Produk cocok, catatan angka/typo lokal | 2 |", "| Cocok sendiri melalui review visual, termasuk dua transcript duplikat | 25 |", "| Tidak ada indikasi kuat otomatis; belum diverifikasi visual | 168 |", "| Total | 200 |", "",
             "Dari 19 flag audit lama, 13 masih terflag oleh screening OCR mentah; seluruh 13 sudah memiliki keputusan visual. Enam false alarm lama keluar dari daftar otomatis: " + ", ".join(sorted(old_names - new_names)) + ". Tidak ada flag otomatis baru.", "",
             details, "## Pemeriksaan visual tambahan setelah Colab", "",
             "Tujuh foto dipilih dari lima overlap terendah yang belum diperiksa (di bawah 60%) dan dua kandidat lain dengan kemiripan lintas transcript. Semua cocok sendiri:", "", "| Foto | Bukti visual |", "|---|---|"]
    lines.extend(f"| {name} | {note} |" for name, note in EXTRA.items())
    lines += ["", "## Metode dan batas interpretasi", "",
              "OCR memakai EasyOCR id/en 1.7.2, lebar maksimum 2000 px, preprocessing dan fungsi reading-order/ekstraksi yang sama. Runtime Colab melaporkan Python 3.13.15, Torch 2.11.0+cu130, Tesla T4. Confidence OCR dicatat sebagai petunjuk kualitas, bukan bukti bahwa teks atau pasangannya benar.", "",
              "Weighted coverage memakai kata unik transcript dan IDF lintas 200 transcript; stopwords generik disisihkan. Skor toleran memakai ratio >=85 untuk kata >=5 huruf. Flag: coverage toleran <45%, atau kandidat transcript lain memiliki exact coverage >=65% dan keunggulan >=20 poin serta minimal lima kata. Diagnostik kata melekat tersedia terpisah. Ini heuristik screening data, tidak mengubah threshold/logic matcher produksi.", "",
              "Pencarian lima kandidat dilakukan dua arah untuk semua 200: foto→transcript dan transcript→foto. Ranking tinggi dapat muncul karena transcript pendek/subset, sehingga keputusan pemetaan harus didukung label visual. Pemeriksaan ini tidak menghitung kinerja matcher pada 160 foto evaluasi dan tidak digunakan untuk tuning matcher.", "",
              "## Verifikasi dan berkas", "",
              f"- {len(protected)} input terlindungi, termasuk seluruh 200 foto, transcript, GT final kalibrasi, KB snapshot, matcher, reader dan tokenizer: hash tetap sama.",
              f"- {len(manifest)} input bundle cocok manifest. Seluruh 160 cache baru dan 40 cache kalibrasi valid; total {detections} deteksi OCR.",
              "- audit_final_review.xlsx: peta cluster, review 14, audit 200, bukti visual 32, ringkasan verifikasi, ranking dua arah. Kolom keputusan pengguna dari cluster_review.xlsx dibawa tanpa ditimpa.",
              "- audit_final_review.csv dan post_colab_visual_review.json: data review final yang dapat diproses ulang.",
              "- post_colab_verification.json: bukti kelengkapan, runtime, integritas dan hash cache.",
              "- Berkas audit_complete.* dan summary_complete.json hasil Colab tetap dipertahankan sebagai hasil sebelum tambahan review lokal tujuh foto.", "",
              "## Menunggu konfirmasi pemetaan sebelum koreksi", "",
              "Belum ada koreksi transcript/GT atau implementasi Prioritas 2–3. Konfirmasi yang diperlukan sesuai permintaan pengguna sebelumnya: peta lima transcript salah pasang, pembuatan transcript baru untuk foto datar_047 dan melengkung_049, serta catatan angka melengkung_003 dan typo melengkung_017. Hanya melengkung_049 dari lima salah pasang berada dalam split kalibrasi; empat lainnya berada dalam evaluasi. Koreksi nanti harus mengikuti filename foto, tanpa memindahkan foto atau mengubah split.", ""]
    (OUT / "laporan_audit_final.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in verification.items() if k != "cache_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
