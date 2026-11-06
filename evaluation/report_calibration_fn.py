"""Susun laporan diagnostik dari bukti tersimpan; tidak mengubah input evaluasi."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation/results/colab_v4/fn_diagnostic"


def main():
    evidence = json.loads((OUT / "evidence.json").read_text(encoding="utf-8"))
    for filename, expected in evidence["input_sha256"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected, filename
    frequency = evidence["frequency"]
    palm = next(row["standard_name"] for row in frequency if row["standard_name"].startswith("Minyak sawit /"))
    samples = [
        ("datar_055.jpeg", frequency[0]["standard_name"], "Lainnya", "Top-1 per token", "ADA: Rerfga Sintetik", "Skor target 74,74, tetapi token memilih Karmin/Anato 79,01. OCR rusak ikut memperburuk persaingan."),
        ("datar_004.jpeg", "Susu sapi", "Lainnya", "Top-1 per token", "ADA: Susu", "Susu 100 berada satu token dengan Perisa Sintetik 100. Tie-break memilih perisa; satu token hanya menghasilkan satu bahan."),
        ("datar_018.jpeg", "Garam", "Lainnya", "Top-1 per token", "ADA: Salt", "Salt 100 berada satu token panjang dengan Cocoa 100; token memilih kakao."),
        ("melengkung_092.jpeg", frequency[3]["standard_name"], "Lainnya", "Tokenizer / penentu bersama", "ADA: Perisa (Sintetik; Alami)", "Tokenizer memisahkan Perisa (Sintetik dan Alami). Skor masing-masing ke Perisa alami 49,42 dan 29,25. Nilai maksimum 69,49 berasal dari Pewarna Alami, bahan berbeda; bukan bukti perisa hampir lolos."),
        ("melengkung_049.jpeg", frequency[4]["standard_name"], "Lainnya", "Top-1 per token", "ADA: Penstabi Nabatl", "Target kelompok nabati 84,78, tetapi token memilih Perisa buatan 90,28. Transcript menyebut Pengemulsi, foto menyebut Penstabil; keduanya berada dalam standard_name kelompok yang sama."),
        ("datar_004.jpeg", "Susu bubuk full cream", "Lainnya", "Top-1 per token", "ADA: Susu Bubuk", "Alias Susu bubuk memperoleh 100, tetapi token yang sama memilih Perisa Sintetik 100. Penyebutan full cream tidak wajib bagi alias KB saat ini."),
        ("datar_070.jpeg", "Pewarna karamel", "Lainnya", "Top-1 per token", "ADA: 'Karamel", "Target karamel 84,32 kalah dari Dinatrium Inosinat 100 di token gabungan; urutan baca dan hilangnya pemisah turut berperan."),
        ("datar_036.jpeg", "Dinatrium Guanilat", "Kesenjangan variant", "Penentu bersama; OCR ikut berperan", "SEBAGIAN: Guanilat), kepala Dinatrium terpisah", "Transcript menggunakan Dinatrium Inosinat dan Guanilat. KB punya Dinatrium Guanilat, E627, Disodium Guanylate, INS 627, INS627, belum pola kepala bersama. Guanilat) sendiri hanya 31,64. OCR menyisipkan tabel gizi di antara kepala dan Guanilat. Skor 75,43 pada transcript justru berasal dari Dinatrium Inosinat, zat berbeda."),
        ("melengkung_036.jpeg", "Gula pasir murni", "Teks ada, skor di bawah 70", "Tokenizer / tanda baca melekat", "ADA: Gula(mengandung", "Alias Gula sudah ada. Tokenisasi whitespace mempertahankan Gula(mengandung sebagai satu kata; skor ke Gula 18,84. Maksimum target 41,81 berasal dari window lain dan bukan penyebutan gula. Transcript dengan spasi Gula (mengandung...) memberi 100."),
        ("datar_015.jpeg", "Dinatrium Inosinat", "OCR / reading-order / ekstraksi", "OCR rusak / frasa terpecah", "SEBAGIAN: Im Inosinat (E631)", "Frasa sasaran memperoleh 63,02 dan tidak lolos. Kepala Dinatrium rusak/terpisah; tanda kurung pada kode E631 ikut menurunkan kecocokan. Maksimum 67,22 berasal dari Dinatrium 'Juanilai (guanilat), bukan inosinat."),
        ("melengkung_049.jpeg", "Natrium bikarbonat (soda kue)", "Lainnya", "Transcript berbeda dengan foto", "TIDAK ADA; yang ada natrium sitrat/malat", "Foto diperiksa visual: label Teh Hitam/Apple memakai natrium sitrat, bukan bikarbonat. Transcript menyebut Teh Oolong dan natrium bikarbonat. Ini ketidaksesuaian foto-transcript, bukan alasan menambahkan alias antara zat berbeda."),
        ("melengkung_049.jpeg", "Sukrosa", "Lainnya", "Transcript berbeda dengan foto", "TIDAK ADA; yang ada steviol glikosida", "Transcript menyebut Ester Sukrosa; foto yang sama menyebut Steviol Glikosida. Pemeriksaan visual mengonfirmasi produk/komposisi berbeda. Skor tertinggi 40,48 merupakan kemiripan kebetulan."),
        ("melengkung_058.jpeg", "Sukralosa", "OCR / reading-order / ekstraksi", "Reading-order lalu pemotongan", "ADA di OCR mentah: Sueralosa); HILANG setelah ekstraksi", "Sueralosa) bernilai 75,53 pada teks OCR lengkap, tetapi bloknya berada sebelum opening-marker Komposisi akibat urutan baca. Ekstraksi membuang blok sebelum marker; maksimum target setelah ekstraksi tinggal 44,14 dari teks tidak terkait."),
        ("melengkung_021.jpeg", "Natrium Benzoat", "OCR / reading-order / ekstraksi", "OCR rusak / frasa terpecah", "SEBAGIAN: Vitamin Benzoat", "Kepala Natrium tidak utuh dalam hasil OCR/urutan baca; Vitamin Benzoat hanya 67,55. Transcript menyebut Pengawet (Natrium Benzoat. Alias zat sudah tersedia."),
        ("datar_036.jpeg", palm, "Lainnya", "Top-1 per token / spesifisitas", "ADA: Minyak Kelapa Sawlt", "Minyak sawit 93,84 kalah dari Minyak kelapa 100 karena kata Sawit rusak menjadi Sawlt. Aturan spesifisitas yang sebelumnya disetujui hanya berada di helper anotasi, bukan matcher produksi."),
    ]
    cases = {(case["filename"], case["standard_name"]): case for case in evidence["cases"]}
    manual = []
    for index, (filename, name, root, subtype, present, explanation) in enumerate(samples, 1):
        case = cases[filename, name]
        best = case["ocr_candidates"][0]
        manual.append(dict(index=index, filename=filename, standard_name=name, category=case["category"], root_cause=root, subtype=subtype, presence=present, explanation=explanation, best_numeric_target_score=best["score"], best_numeric_window=best["window"], winner=best["winner"].get("standard_name")))
    roots = Counter(row["root_cause"] for row in manual)
    summary = {"threshold": 70, "fn_total": 168, "distinct_ingredients": 78, "manual_sample_count": 15,
               "distinct_sample_photos": len({row["filename"] for row in manual}),
               "manual_root_counts": dict(roots), "manual_root_percent": {key: round(value / 15 * 100, 1) for key, value in roots.items()},
               "manual_subtype_counts": dict(Counter(row["subtype"] for row in manual)),
               "numeric_target_score_at_least_70": sum(bool(case["ocr_candidates"] and case["ocr_candidates"][0]["score"] >= 70) for case in evidence["cases"]),
               "limitation": "Sampel purposif, bukan sampel acak. Proporsi tidak boleh diekstrapolasi menjadi jumlah pasti dari 168. Skor maksimum dapat berasal dari zat/frasa berbeda.",
               "protected_inputs_sha256_verified": True}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "manual_15.json").write_text(json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Diagnostik FN kalibrasi — threshold 70", "", "## Ruang lingkup dan metode", "",
             "Seluruh 168 FN (pasangan filename + standard_name) di 40 foto berasal dari grid_detail.csv threshold 70. Ada 78 standard_name berbeda. Cache OCR Colab dipakai kembali; OCR tidak dijalankan ulang. Teks dibangun ulang menggunakan sort_reading_order, extract_composition_section dan tokenize produksi yang tidak diubah. Skor dihitung dengan find_best_window dan pemenang aktual dengan match_token threshold 70; alias dan bobot sama dengan grid search. Hash tujuh input utama diverifikasi tetap sama setelah audit.", "",
             "Sepuluh kasus utama mewakili sepuluh bahan dengan frekuensi FN tertinggi; lima tambahan dipilih untuk membedakan akar masalah. Total 15 pasangan dari 11 foto, mencakup aman, perhatian dan hindari. Sampel purposif: persentase di bawah hanya proporsi sampel, bukan estimasi statistik seluruh 168. Label akar utama bisa memiliki faktor sekunder.", "",
             "## Frekuensi 15 besar", "", "| Standard name | FN |", "|---|---:|"]
    lines.extend(f"| {row['standard_name']} | {row['count']} |" for row in frequency[:15])
    lines += ["", "Top 15 mencakup 78/168 FN (46,4%). Semua 78 frekuensi dan semua 168 jejak tersedia di Excel/CSV/evidence.json.", "", "## Proporsi akar masalah — audit manual 15 kasus", "", "| Akar utama | Kasus | Persentase sampel |", "|---|---:|---:|"]
    lines.extend(f"| {key} | {value} | {value / 15 * 100:.1f}% |" for key, value in roots.items())
    lines += ["", "Lainnya terdiri dari tujuh kasus top-1 per token (46,7% sampel), satu pemisahan penentu frasa oleh tokenizer (6,7%), dan dua FN akibat transcript berbeda dari foto (13,3%). Tiga kasus upstream terdiri dari dua frasa OCR rusak/terpecah dan satu bahan yang ada di OCR tetapi dibuang saat ekstraksi karena urutan baca. Kesenjangan variant satu kasus memiliki faktor OCR sekunder.", "",
              f"Dari seluruh 168, {summary['numeric_target_score_at_least_70']} mempunyai setidaknya satu skor numerik target >=70. Angka ini bukan jumlah FN yang pasti bisa dipulihkan: kemiripan dapat berasal dari zat lain. Bukti kuat hambatan selain threshold adalah tujuh kasus manual yang penyebutan targetnya terkonfirmasi, skornya >=70, tetapi kalah dari pemenang token. Menurunkan threshold saja tidak membuat matcher top-1 mengeluarkan bahan kedua.", "",
              "Tidak ada perubahan pada dataset, GT, KB, threshold, algoritma matcher, negasi, closing-marker atau reading-order. Kasus taxonomy/generic-vs-specific tetap diperlakukan sebagai anotasi yang diberikan, tanpa memutuskan taksonomi klinis baru.", "",
              "## Sepuluh perbandingan lengkap dan lima kasus tambahan", "",
              "Setiap kasus menyertakan transcript asli lengkap (jadi konteks di sekitar bahan tidak dipotong), seluruh OCR setelah reading-order, seluruh hasil ekstraksi yang benar-benar diproses, token, alias dan tiga kandidat skor. Skor numerik maksimum tidak selalu berasal dari penyebutan bahan yang benar; penjelasan manual harus dibaca bersama jejak skor."]
    for row in manual:
        case = cases[row["filename"], row["standard_name"]]
        photo = evidence["photos"][row["filename"]]
        lines += ["", f"### {row['index']}. {row['filename']} — {row['standard_name']}", "",
                  f"Kategori: {row['category']}. Kehadiran: **{row['presence']}**. Akar utama: **{row['root_cause']}** ({row['subtype']}).", "", row["explanation"], "",
                  "Anotasi GT: `" + json.dumps(case["ground_truth_ingredient"], ensure_ascii=False) + "`", "",
                  "Alias KB: " + "; ".join(case["kb_variants"]), ""]
        for title, key in [("Ground truth text asli / transcripts.csv", "ground_truth_text"), ("OCR lengkap setelah reading-order, sebelum ekstraksi", "ocr_reading_order_text"), ("Hasil extract_composition_section yang benar-benar diproses", "ocr_composition_text")]:
            lines += [f"**{title}**", "", "```text", photo[key], "```", ""]
        lines += ["**Token aktual dan tiga kandidat target tertinggi**", "", "```json", json.dumps({"tokens": photo["tokens"], "target_candidates": case["ocr_candidates"], "raw_ocr_candidates": case["raw_ocr_candidates"], "transcript_candidates": case["transcript_candidates"]}, ensure_ascii=False, indent=2), "```", ""]
    (OUT / "laporan_fn_threshold70.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    workbook = Workbook()
    workbook.remove(workbook.active)
    def sheet(title, rows):
        ws = workbook.create_sheet(title)
        keys = list(rows[0])
        ws.append(keys)
        for row in rows:
            ws.append([row.get(key) for key in keys])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(70, max(15, len(str(col[0].value)) + 3))
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet("Frekuensi_78", frequency)
    with (OUT / "all_168_fn.csv").open(encoding="utf-8-sig", newline="") as source:
        sheet("Seluruh_168_FN", list(csv.DictReader(source)))
    sheet("Audit_manual_15", manual)
    sheet("Proporsi_sampel", [dict(root_cause=key, count=value, percent=round(value / 15 * 100, 1)) for key, value in roots.items()])
    sheet("Teks_foto_sampel", [{key: value for key, value in evidence["photos"][filename].items() if key not in ("tokens", "predicted_at_70")} for filename in dict.fromkeys(row["filename"] for row in manual)])
    workbook.save(OUT / "fn_diagnostic.xlsx")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
