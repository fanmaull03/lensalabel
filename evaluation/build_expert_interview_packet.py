"""Create an anonymized, blinded expert-interview packet from frozen artifacts.

No OCR or matching is performed. The first PDF section contains only photos and
expert verdict forms; system output appears in a later, separate section.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from pathlib import Path

from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.tokenizer.tokenizer import (  # noqa: E402
    OPEN_MARKERS, _find_closing_marker, _find_marker,
)

EVAL_GT = ROOT / "evaluation/ground_truth/evaluation_gt_kb_v2_final.json"
SPLIT = ROOT / "evaluation/splits/evaluation_set.csv"
CACHE = ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"
PHOTOS = ROOT / "dataset/raw_photos"
OUT = ROOT / "evaluation/results/expert_interview"
THREE = {"aman": "aman", "perhatian": "perhatian", "hindari": "hindari"}
STATUS_TO_3 = {**THREE, "perlu_verifikasi": "perhatian", "tidak_terbaca": "perhatian"}
VERDICT_TEXT = {
    "aman": "Tidak ditemukan bahan yang melanggar diet GFCF.",
    "perhatian": "Ada bahan yang perlu dicermati. Periksa daftarnya di bawah sebelum memutuskan.",
    "hindari": "Ditemukan bahan yang sebaiknya dihindari pada diet GFCF.",
    "perlu_verifikasi": "Bahan yang terbaca tergolong aman, tapi ada bagian komposisi yang tidak dikenali sistem. Periksa label aslinya.",
    "tidak_terbaca": "Sistem tidak berhasil membaca komposisi apa pun dari foto ini.",
}


def gt_verdict(item: dict) -> str:
    cats = {x["category"].casefold() for x in item.get("ingredients", [])}
    return "hindari" if "hindari" in cats else "perhatian" if "perhatian" in cats else "aman"


def load_data():
    gt = json.loads(EVAL_GT.read_text(encoding="utf-8"))
    with SPLIT.open(encoding="utf-8-sig", newline="") as f:
        split = {r["filename"]: r["category"] for r in csv.DictReader(f)}
    cache_rows = [json.loads(s) for s in CACHE.read_text(encoding="utf-8").splitlines() if s.strip()]
    cache = {r["filename"]: r["prediction"] for r in cache_rows if r.get("record_type") == "photo"}
    ocr_rows = {}
    with (ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv").open(encoding="utf-8-sig", newline="") as f:
        ocr_rows = {r["filename"]: r for r in csv.DictReader(f)}
    if set(gt) != set(split) or set(gt) != set(cache) or set(gt) != set(ocr_rows):
        raise ValueError("Split, GT, cache prediksi, dan cache OCR tidak memiliki himpunan foto yang sama.")
    return gt, split, cache, ocr_rows


def select_cases(gt: dict, split: dict, predictions: dict, *, seed: int = 42) -> list[dict]:
    """Sample 6 per condition, then one distinct deterministic case per rule."""
    rng = random.Random(seed)
    chosen: list[tuple[str, str]] = []
    for condition in ("datar", "melengkung"):
        pool = sorted(name for name, cond in split.items() if cond == condition)
        if len(pool) < 6:
            raise ValueError(f"Foto {condition} kurang dari enam.")
        chosen.extend((name, "acak_berstrata") for name in rng.sample(pool, 6))
    used = {name for name, _ in chosen}
    remaining = sorted(set(gt) - used)

    def add_first(case_type: str, predicate):
        candidates = [n for n in remaining if predicate(n)]
        if not candidates:
            raise ValueError(f"Tidak ditemukan kasus batas yang memenuhi: {case_type}")
        name = candidates[0]
        chosen.append((name, case_type)); used.add(name); remaining.remove(name)

    add_first("tepat_satu_hindari", lambda n:
              sum(x["category"].casefold() == "hindari" for x in gt[n].get("ingredients", [])) == 1
              and any(x["category"].casefold() in {"aman", "perhatian"} for x in gt[n].get("ingredients", [])))
    add_first("sistem_perlu_verifikasi", lambda n:
              predictions[n].get("classification", {}).get("verdict", predictions[n].get("verdict")) == "perlu_verifikasi")
    c_candidates = [n for n in remaining if gt_verdict(gt[n]) == "hindari"
                    and predictions[n].get("classification", {}).get("verdict", predictions[n].get("verdict")) == "perhatian"]
    if not c_candidates:
        raise ValueError("Tidak ditemukan kasus GT Hindari dan sistem Perhatian.")
    c_name = random.Random(seed).choice(sorted(c_candidates))
    chosen.append((c_name, "gt_hindari_sistem_perhatian_acak_seed42")); used.add(c_name); remaining.remove(c_name)
    # On the KB v2-aligned evaluation the system never emits "aman" as a raw
    # status, so a strict "sistem_aman" case may not exist. Keep the packet
    # buildable by treating that case as optional and noting the omission.
    aman_candidates = [n for n in remaining
                       if predictions[n].get("classification", {}).get("verdict", predictions[n].get("verdict")) == "aman"]
    if aman_candidates:
        chosen.append((aman_candidates[0], "sistem_aman")); used.add(aman_candidates[0])
    else:
        print("Catatan: tidak ada foto dengan status mentah 'aman' pada konfigurasi v2; "
              "slot kasus batas 'sistem_aman' dikosongkan.", flush=True)
    return [{"id": f"W{i:02d}", "filename": name, "condition": split[name], "case_type_research_only": kind}
            for i, (name, kind) in enumerate(chosen, start=1)]


def _pdf_escape(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 78) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + bool(line) > width:
            lines.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line: lines.append(line)
    return lines


class SimplePDF:
    """Small self-contained PDF writer; embeds compressed JPEG previews."""
    def __init__(self): self.pages = []

    def add_page(self, lines: list[tuple[float, float, int, str]], image_bytes: bytes | None = None, img_w: int = 0, img_h: int = 0):
        content = []
        if image_bytes:
            # Image placed below title/form area.
            box_w, box_h = 520.0, 470.0
            scale = min(box_w / img_w, box_h / img_h)
            w, h = img_w * scale, img_h * scale
            x, y = (612 - w) / 2, 205 + (box_h - h) / 2
            content.append(f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /Im0 Do Q")
        for x, y, size, text in lines:
            content.append(f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td ({_pdf_escape(text)}) Tj ET")
        self.pages.append(("\n".join(content).encode("cp1252", errors="replace"), image_bytes, img_w, img_h))

    def write(self, path: Path):
        objects: list[bytes] = []
        def obj(data: bytes) -> int:
            objects.append(data); return len(objects)
        catalog_id = obj(b"")
        pages_id = obj(b"")
        font_id = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        page_ids = []
        for content, image, iw, ih in self.pages:
            content_id = obj(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
            image_ref = b""
            resources = f"/Font << /F1 {font_id} 0 R >>".encode()
            if image:
                image_id = obj(b"<< /Type /XObject /Subtype /Image /Width " + str(iw).encode() + b" /Height " + str(ih).encode() +
                               b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length " + str(len(image)).encode() + b" >>\nstream\n" + image + b"\nendstream")
                resources += b" /XObject << /Im0 " + str(image_id).encode() + b" 0 R >>"
            page_id = obj(b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R /MediaBox [0 0 612 792] /Resources << " + resources +
                          b" >> /Contents " + str(content_id).encode() + b" 0 R >>")
            page_ids.append(page_id)
        objects[catalog_id - 1] = b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>"
        objects[pages_id - 1] = b"<< /Type /Pages /Kids [" + b" ".join(f"{i} 0 R".encode() for i in page_ids) + b"] /Count " + str(len(page_ids)).encode() + b" >>"
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets = [0]
        for i, data in enumerate(objects, start=1):
            offsets.append(len(output)); output.extend(f"{i} 0 obj\n".encode()); output.extend(data); output.extend(b"\nendobj\n")
        xref = len(output); output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
        for off in offsets[1:]: output.extend(f"{off:010d} 00000 n \n".encode())
        output.extend(f"trailer\n<< /Size {len(offsets)} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
        path.write_bytes(output)


def _preview(photo: Path) -> tuple[bytes, int, int]:
    with Image.open(photo) as im:
        im = im.convert("RGB"); im.thumbnail((1400, 1100))
        buff = io.BytesIO(); im.save(buff, format="JPEG", quality=78, optimize=True)
        return buff.getvalue(), *im.size


def build_pdf(cases: list[dict], predictions: dict):
    pdf = SimplePDF()
    # All expert-only forms precede the section containing any system output.
    for case in cases:
        photo, iw, ih = _preview(PHOTOS / case["condition"] / case["filename"])
        lines = [(48, 754, 17, f"Penilaian ahli - {case['id']}"),
                 (48, 730, 10, "Bagian I. Isi verdict ahli sebelum membuka Bagian II."),
                 (48, 190, 11, "Verdict ahli:  [ ] Aman   [ ] Perlu Perhatian   [ ] Hindari"),
                 (48, 164, 10, "Bahan yang menjadi dasar verdict / bagian label yang perlu diperiksa:"),
                 (48, 144, 10, "________________________________________________________________________"),
                 (48, 122, 10, "Catatan:"), (48, 101, 10, "________________________________________________________________________"),
                 (48, 80, 10, "________________________________________________________________________")]
        pdf.add_page(lines, photo, iw, ih)
    for case in cases:
        pred = predictions[case["filename"]]
        raw_status = pred.get("classification", {}).get("verdict", pred.get("verdict", "tidak_terbaca"))
        text_rows = [f"Verdict sistem: {raw_status.replace('_', ' ').title()}"]
        text_rows.extend(_wrap(VERDICT_TEXT.get(raw_status, ""), 88))
        for category in ("hindari", "perhatian", "aman"):
            items = pred.get("classification", {}).get(category, [])
            if not items:
                continue
            text_rows.append(f"{category.title()} ({len(items)}):")
            for item in items:
                matched = (item.get("matched_window") or "").replace("\n", " ")
                text_rows.extend(_wrap(f"{item.get('standard_name', '')} | terbaca: {matched}", 86))
        unknown = pred.get("classification", {}).get("tidak_dikenali", [])
        if unknown:
            text_rows.append(f"Tidak dikenali sistem ({len(unknown)}):")
            for item in unknown:
                text_rows.extend(_wrap(f"{item.get('token', '')} (terdekat: {item.get('terdekat', '')})", 86))
        text_rows.extend(_wrap("Catatan rinci aplikasi bersifat umum sesuai kategori, bukan petunjuk konsumsi khusus per bahan.", 88))
        chunks = [text_rows[i:i + 42] for i in range(0, len(text_rows), 42)] or [[]]
        for page_idx, chunk in enumerate(chunks):
            title = f"Tampilan ringkas keluaran aplikasi - {case['id']}" + (" (lanjutan)" if page_idx else "")
            lines = [(48, 754, 17, title)]
            if page_idx == 0:
                lines.append((48, 729, 10, "Bagian II - keluaran sistem untuk ditinjau setelah seluruh verdict ahli dicatat."))
            y = 698 if page_idx == 0 else 724
            for row in chunk:
                lines.append((56, y, 9, row)); y -= 13
            pdf.add_page(lines)
        pdf.add_page([(48, 754, 16, f"Penilaian penyajian - {case['id']}"),
                      (48, 718, 11, "Kesesuaian keluaran aplikasi:  [ ] Sesuai   [ ] Sebagian   [ ] Tidak Sesuai"),
                      (48, 686, 10, "Catatan ahli:"), (48, 663, 10, "________________________________________________________________________"),
                      (48, 640, 10, "________________________________________________________________________"),
                      (48, 605, 9, "Skor aspek 1-4 dan pertanyaan terbuka tersedia pada template respons terpisah.")])
    pdf.write(OUT / "paket_wawancara_ahli_gizi_v2.pdf")


def build_template(cases):
    wb = Workbook(); ws = wb.active; ws.title = "verdict_ahli"
    ws.append(["id_anonim", "verdict_ahli", "catatan_verdict"])
    for c in cases: ws.append([c["id"], "", ""])
    ui = wb.create_sheet("penyajian_aplikasi")
    ui.append(["id_anonim", "kesesuaian", "kejelasan_istilah_1_4", "urutan_informasi_1_4", "keterangan_konsumsi_1_4", "kelayakan_skrining_1_4", "catatan"])
    for c in cases: ui.append([c["id"], "", "", "", "", "", ""])
    op = wb.create_sheet("pertanyaan_terbuka")
    op.append(["pertanyaan", "jawaban_ahli"])
    for q in ["Informasi apa yang paling membantu saat menilai verdict?", "Istilah atau urutan informasi apa yang perlu diperjelas?", "Informasi konsumsi apa yang dibutuhkan tetapi belum tersedia?", "Dalam situasi apa hasil perlu dikonfirmasi dari label atau tenaga kesehatan?", "Saran lain untuk penggunaan sebagai alat bantu skrining?"]:
        op.append([q, ""])
    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"; sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="17365D")
        for col in sheet.columns:
            letter = col[0].column_letter
            sheet.column_dimensions[letter].width = min(48, max(14, max(len(str(c.value or "")) for c in col) + 2))
        for row in sheet.iter_rows():
            for cell in row: cell.alignment = Alignment(vertical="top", wrap_text=True)
    wb.save(OUT / "template_respons_wawancara_v2.xlsx")


def build_instrument():
    path = ROOT / "docs/evaluation/expert_interview_instrument.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""# Instrumen wawancara terstruktur ahli gizi\n\nInstrumen ini mengikuti Skema Ketiga Sub-bab 3.4.5: satu sesi setelah demonstrasi purwarupa. Ahli terlebih dahulu menilai verdict dari foto label tanpa melihat keluaran sistem. Setelah semua verdict awal dicatat, Bagian II memperlihatkan keluaran sistem dan meminta penilaian kesesuaian serta keterpakaian.\n\n## Penilaian verdict independen\n\nUntuk setiap foto, tentukan verdict produk berdasarkan komposisi yang tercetak: **Aman**, **Perlu Perhatian**, atau **Hindari**. Catat bahan atau bagian label yang menjadi dasar penilaian dan catatan klinis yang relevan. Jangan membuka Bagian II sebelum mengisi seluruh verdict di Bagian I.\n\n## Kesesuaian keluaran\n\nSetelah melihat tampilan ringkas aplikasi, pilih satu: **Sesuai**, **Sebagian**, atau **Tidak Sesuai**. Catat alasannya.\n\n## Skala penilaian penyajian\n\nGunakan skala 4 poin untuk setiap aspek: **1 = Sangat kurang**, **2 = Kurang**, **3 = Baik**, **4 = Sangat baik**.\n\n- Kejelasan istilah yang digunakan.\n- Urutan informasi hasil (verdict, daftar bahan, dan rincian bahan).\n- Keterangan konsumsi yang ditampilkan.\n- Kelayakan sebagai alat bantu skrining awal.\n\n## Pertanyaan terbuka\n\n1. Informasi apa yang paling membantu saat menilai verdict?\n2. Istilah atau urutan informasi apa yang perlu diperjelas?\n3. Keterangan konsumsi apa yang dibutuhkan tetapi belum tersedia pada tampilan?\n4. Dalam situasi apa hasil perlu dikonfirmasi dari label atau tenaga kesehatan?\n5. Apa saran lain untuk penggunaan sebagai alat bantu skrining?\n\n## Batas tampilan yang dinilai\n\nImplementasi antarmuka saat ini menampilkan nama bahan, badge kategori, teks yang terbaca, skor kecocokan, catatan generik tingkat kategori, dan disclaimer ilmiah generik. Catatan tingkat kategori menjelaskan kategori, bukan petunjuk konsumsi spesifik per bahan. Aplikasi tidak menampilkan catatan konsumsi khusus per bahan dari basis data. Karena itu, nilai aspek keterangan konsumsi berdasarkan informasi generik yang benar-benar terlihat dan tuliskan kebutuhan informasi tambahan; jangan menganggap aplikasi sudah menyajikan arahan konsumsi klinis khusus.\n\n## Data dan anonimitas\n\nKasus diberi ID W01–W16. Dokumen ahli tidak menampilkan nama file atau jenis pemilihan kasus. Kunci ID disimpan terpisah oleh peneliti. Jangan mencatat nama, nomor telepon, alamat email, atau data kontak ahli dalam lembar respons.\n""", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    gt, split, predictions, _ = load_data()
    cases = select_cases(gt, split, predictions, seed=args.seed)
    with (OUT / "case_key_research_only_v2.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "filename", "condition", "case_type_research_only"]); w.writeheader(); w.writerows(cases)
    build_pdf(cases, predictions); build_template(cases); build_instrument()
    inputs = [SPLIT, EVAL_GT, CACHE, ROOT / "evaluation/results/evaluation_ocr/evaluation_ocr_160.csv", ROOT / "evaluation/config_frozen.json"]
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    (OUT / "packet_metadata_v2.json").write_text(json.dumps({"seed": args.seed, "random_selection": "6 datar + 6 melengkung dari evaluation split, tanpa kondisi hasil", "n_random_stratified": 12, "n_boundary": 4, "case_count": len(cases), "input_sha256": hashes, "ocr_or_matching_rerun": False, "case_type_labels_in_expert_pdf": False, "expert_forms_precede_system_output": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "strata": {c: sum(x["condition"] == c for x in cases[:12]) for c in ("datar", "melengkung")}, "pdf": str(OUT / "paket_wawancara_ahli_gizi_v2.pdf"), "template": str(OUT / "template_respons_wawancara_v2.xlsx"), "research_key": str(OUT / "case_key_research_only_v2.csv")}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
