"""Render audit tables without altering KB, GT, or the reviewed workbooks."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/secondary_guard_audit'

def readcsv(name):
    return list(csv.DictReader((OUT/name).open(encoding='utf-8-sig')))

def pct(value):
    return f'{100*float(value):.2f}%'.replace('.',',')

def main():
    rows=readcsv('ablation_summary.csv')
    dist=json.loads((OUT/'score_distributions.json').read_text(encoding='utf-8'))
    src=json.loads((OUT/'source_review_summary.json').read_text(encoding='utf-8'))
    complete=json.loads((OUT/'completion.json').read_text(encoding='utf-8'))
    assert len(rows)==96 and complete['complete']
    wb=openpyxl.Workbook();sheet=wb.active;sheet.title='ablasi_96'
    headings=['konfigurasi','threshold','TP','FP','FN','precision','recall','F1','FN_pulih_bertahan','FP_baru_terbuang','FN_pulih_hilang','TP_lama_hilang']
    sheet.append(headings)
    for r in rows:
        sheet.append([r[k] if k=='config' else float(r[k]) if k in ('precision','recall','f1') else int(r[k])
                      for k in ('config','threshold','tp','fp','fn','precision','recall','f1','fn_still_recovered','new_fp_removed','recovered_lost','existing_tp_lost')])
    for col in 'FGH':
        for cell in sheet[col][1:]:cell.number_format='0.00%'
    sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    sheet.column_dimensions['A'].width=21
    for col in 'BCDEFGHIJKL':sheet.column_dimensions[col].width=19
    for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17324D')
    summary=wb.create_sheet('cara_membaca')
    for item,meaning in [
        ('A','Batas skor tambahan saja: 80, 85, atau 90; OFF=tidak dipakai.'),
        ('B','Cakupan semua kata varian multi-kata dan penolakan dukungan yang hanya kata generik; berlaku hanya match tambahan.'),
        ('C','Batasi posisi match tambahan sesudah marker gizi/anjuran jika ditemukan setelah pembuka. Match pertama setiap token dilindungi.'),
        ('FN_pulih_bertahan','Bahan yang FN pada matcher lama tetapi TP pada matcher baru pada threshold yang sama dan tetap TP setelah pengaman.'),
        ('FP_baru_terbuang','FP tambahan matcher baru terhadap matcher lama yang hilang pada threshold yang sama.'),
        ('dasar','GT baru 396 bahan, 40 foto, KB dan cache OCR sama. Nilai 70-95.'),
        ('peringatan_C','Pemotongan teks mentah C bukan perubahan aman global: delapan foto berisiko kehilangan bahan sah karena urutan OCR.'),
    ]:summary.append([item,meaning])
    summary.column_dimensions['A'].width=22;summary.column_dimensions['B'].width=110
    wb.save(OUT/'ablasi_96.xlsx')

    chosen=['Aoff_B0_C0','A80_B0_C0','A85_B0_C0','A90_B0_C0','Aoff_B1_C0','Aoff_B0_C1','A80_B1_C0','A80_B1_C1']
    by={(r['config'],int(r['threshold'])):r for r in rows}
    lines=['# Audit pengaman match kedua — 8 Oktober 2026','',
        'Seluruh pengaman opt-in dan **default OFF**. GT, KB, foto, split, review manual, reading-order, dan aturan negasi tidak berubah. Matcher pertama pada tiap token tetap identik; 80 pemanggilan nyata (5 foto × 16 konfigurasi) cocok persis dengan replay jejak yang disimpan. Suite: 111 tes + 80 subtes lulus.','',
        '## Analisis 68 FN pulih dan 45 FP tambahan (threshold 70)','',
        '| Ukuran | FN pulih | FP baru |','|---|---:|---:|',
        f"| Skor min / median / maks | {dist['recovered_false_negative']['score_min']:.2f} / {dist['recovered_false_negative']['score_median']:.2f} / {dist['recovered_false_negative']['score_max']:.2f} | {dist['new_false_positive']['score_min']:.2f} / {dist['new_false_positive']['score_median']:.2f} / {dist['new_false_positive']['score_max']:.2f} |",
        f"| Cakupan seluruh kata varian | {dist['recovered_false_negative']['full_coverage']}/68 | {dist['new_false_positive']['full_coverage']}/45 |",
        f"| Dukungan hanya kata generik | {dist['recovered_false_negative']['generic_only']}/68 | {dist['new_false_positive']['generic_only']}/45 |",
        f"| Risiko panel menurut heuristik otomatis | {dist['recovered_false_negative']['panel_context_risk']}/68 | {dist['new_false_positive']['panel_context_risk']}/45 |",
        f"| Pemeriksaan konteks sumber: di luar komposisi | {src['recovered_false_negative']['LUAR_KOMPOSISI']}/68 | {src['new_false_positive']['LUAR_KOMPOSISI']}/45 |",
        f"| Pemeriksaan konteks sumber: tidak pasti | 0/68 | {src['new_false_positive']['SUMBER_OCR_TIDAK_PASTI']}/45 |",
        '',
        'Cakupan kata memakai alignment berurutan satu kata sumber untuk satu kata varian, kemiripan ≥85%; kode bernomor wajib persis. Kata generik tercantum dalam `backend/app/matching/secondary_guards.py`. Proporsi ini adalah bukti leksikal pada OCR, bukan validasi zat secara klinis. Review sumber memakai potongan OCR dan tidak menggantikan pemeriksaan foto. Satu TP pemulihan (`Gula`, melengkung_001) justru berasal dari tabel gizi, meski nama Gula ada di GT. Karena itu 68 adalah angka metrik, bukan 68 bukti bahan sah dari komposisi.','',
        '## Ablasi pada threshold utama 70','',
        '| Flag | TP | FP | FN | P | R | F1 | FN pulih bertahan | FP baru terbuang |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key in chosen:
        r=by[key,70]
        lines.append(f"| {key} | {r['tp']} | {r['fp']} | {r['fn']} | {pct(r['precision'])} | {pct(r['recall'])} | {float(r['f1']):.4f} | {r['fn_still_recovered']} | {r['new_fp_removed']} |")
    lines.extend(['',
        'A=80 adalah titik uji paling seimbang pada threshold 70: F1 0,7837, mempertahankan 51/68 FN yang pulih dan membuang 34/45 FP baru. B sendiri membuang 23 FP tetapi kehilangan 17 FN yang tadinya pulih. C sendiri membuang 9 FP dan kehilangan 3 FN pulih. Gabungan A80+B+C membuang 41 FP tetapi mempertahankan hanya 40 FN pulih. Tidak ada flag atau threshold yang diaktifkan otomatis.','',
        '## Semua threshold 70–95','',
        'Tabel berikut menampilkan baseline dan semua pengaman tunggal. Seluruh **16 konfigurasi × 6 threshold**, termasuk setiap gabungan A/B/C, tersedia di `ablasi_96.xlsx` dan `ablation_summary.csv`; detail per foto ada di `ablation_detail.csv`. Kolom FN pulih dan FP terbuang selalu dihitung terhadap matcher lama pada **threshold yang sama**, sehingga penyebutnya berubah antar-threshold.','',
        '| Flag | Threshold | P | R | F1 | FN pulih bertahan | FP baru terbuang |','|---|---:|---:|---:|---:|---:|---:|'])
    for key in chosen[:6]:
        for t in (70,75,80,85,90,95):
            r=by[key,t]
            lines.append(f"| {key} | {t} | {pct(r['precision'])} | {pct(r['recall'])} | {float(r['f1']):.4f} | {r['fn_still_recovered']} | {r['new_fp_removed']} |")
    lines.extend(['',
        '## Penanda panel dan regresi 200 foto','',
        'C menambah delapan marker yang diminta: Takaran Saji, Serving Size, Informasi Nilai Gizi, Nutrition Facts, Jumlah Per Sajian, Energi Total, Persen AKG, Konsumsi Gula. Marker dicari **setelah** marker pembuka; `Garam (Natrium)` tidak menjadi marker. Default fungsi ekstraksi sama dengan versi sebelum perubahan. Pengujian closing-marker A–E lolos pada flag OFF dan ON.','',
        f"Pada OCR mentah 200 foto, ekstraksi dengan C berubah di **{complete['ocr_changed']} foto**, sementara pada 200 transcript bersih **{complete['transcript_changed']} berubah**. Audit konservatif menemukan **{complete['potential_loss_photos']} foto berpotensi kehilangan nama bahan sah** yang sebelumnya terbaca OCR dan juga tercantum dalam transcript: datar_017, datar_035, datar_036, datar_042, datar_043, datar_057, melengkung_019, melengkung_033. Semua potongan sebelum/sesudah tercantum di `extraction_regression_200.csv`.",
        'Setidaknya tujuh dari delapan kasus memperlihatkan komposisi sah setelah marker panel yang tersisip oleh reading-order; pada melengkung_019, pemotongan bahkan terjadi sebelum marker Komposisi Indonesia yang benar karena pembuka Inggris lebih awal. Melengkung_033 adalah alarm konservatif: `Gula` yang hilang tampak dari baris gizi, sementara komposisi OCR terbaca `CULA PASIR`. Maka **klaim “tidak ada bahan sah terpotong” tidak terpenuhi** untuk pemotongan global. C dalam ablasi hanya menolak match tambahan sesudah batas, dan selalu mempertahankan match pertama; ia tetap dapat kehilangan FN yang pulih. C tetap OFF.','',
        '## Kandidat GT ejaan menyatu','',
        'Ekspansi review-only menemukan **satu kandidat baru** dari 40 foto: `melengkung_084.jpeg`, **Beta-karoten (pewarna alami)**, kategori `aman`, span `Betacarotene`, varian KB `Beta carotene`. Daftar `new_joined_candidates.xlsx` hanya memuat baris baru ini, keputusan kosong Y/N. Ia belum digabung ke GT dan review v4 lama tetap utuh.','',
        '## Alias KB untuk ahli','',
        'Pertanyaan rinci per alias ada di `alias_untuk_ahli_gizi.md`. Contoh langsung: `Flavor enhancer` di bawah Sweet modulator, `Kari` pada kelompok bumbu rempah, alias `Vitamin A`/`Vitamin D3` untuk kanonis gabungan, dan alias umum yang tidak membuktikan klaim “murni”, “tanpa perisa”, atau “bersertifikat”. KB tidak diubah.','',
        'Batas lain: `Cocoa Butter Substitute`→`Butter` berskor 100 tetap lolos A; B hanya membatasi varian multi-kata dan dukungan generik sehingga tidak menyelesaikan pemotongan frasa satu kata ini. Pemeriksaan konteks/negasi yang lebih luas akan memerlukan keputusan terpisah.',''])
    (OUT/'laporan_pengaman_match_kedua.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Report and workbook written:',len(rows),'rows')

if __name__=='__main__':main()
