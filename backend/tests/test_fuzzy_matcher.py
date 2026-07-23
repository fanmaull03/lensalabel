"""Kunci angka untuk false positive yang sudah ditemukan manual (Tahap 5).

  python -m tests.test_fuzzy_matcher    (atau: pytest tests/test_fuzzy_matcher.py)

Isi file ini SENGAJA menguji perilaku yang SALAH. Tujuannya supaya perubahan
kalibrasi di Tahap 9 (bobot, threshold, penalti panjang kata) ketahuan efeknya
tanpa perlu uji manual lagi: begitu assert di sini mulai gagal, artinya
perilakunya berubah, dan tinggal dicek apakah berubah ke arah yang benar.
"""

from app.matching.fuzzy_matcher import THRESHOLD, composite_score, find_best_window

# Angka hasil pengukuran nyata dengan WEIGHTS & THRESHOLD saat ini (masih
# placeholder 1/3 rata & 75.0). Kalau salah satu knob diubah, angka ini ikut
# bergeser dan test gagal, itu memang sinyal yang diinginkan.
SKOR_SALT_MALT = 75.0


def test_salt_vs_malt_masih_lolos_threshold():
    """'Salt' (garam, aman) lolos jadi 'malt' (barley, sumber gluten).

    Beda satu huruf, makna bertolak belakang. Ditemukan lewat uji end-to-end
    di frontend pakai normal_003.jpeg: verdict produk jadi 'hindari' keliru.
    """
    skor = composite_score("Salt", "malt")
    assert skor == SKOR_SALT_MALT
    # match_token() memakai `best_score < threshold` untuk menolak, jadi skor
    # yang PERSIS sama dengan threshold tetap diterima. Ini yang bikin 'Salt'
    # lolos: 75.0 bukan di atas threshold, tapi tepat di garisnya.
    assert skor >= THRESHOLD, "kalau ini gagal, cek apakah Tahap 9 sudah menutup kasus Salt/malt"


def test_salt_dalam_kalimat_tetap_ketemu_lewat_windowing():
    """Windowing Tahap 5 justru memudahkan false positive ini muncul.

    'Salt' yang terkubur di token panjang tetap terangkat jadi window sendiri,
    sehingga skor 75.0-nya tercapai walau token aslinya jauh lebih panjang.
    """
    window, skor = find_best_window("Wheat Flour Sugar Salt Yeast", "malt")
    assert window == "Salt"
    assert skor == SKOR_SALT_MALT


def test_target_tahap9_belum_tercapai():
    """Status target Tahap 9, dilaporkan tanpa menggagalkan suite.

    Target: 'Salt' TIDAK boleh lolos sebagai 'malt'. Selama belum tercapai,
    fungsi ini cuma mencetak status; yang mengunci angkanya adalah dua test di
    atas. Begitu Tahap 9 menerapkan penalti panjang kata, dua test di atas akan
    gagal, lalu file ini tinggal dibalik jadi assert skor < THRESHOLD.
    """
    sudah_teratasi = composite_score("Salt", "malt") < THRESHOLD
    status = "SUDAH TERATASI" if sudah_teratasi else "MASIH BERMASALAH (diharapkan)"
    print(f"  target Tahap 9 'Salt' bukan 'malt': {status}")


if __name__ == "__main__":
    test_salt_vs_malt_masih_lolos_threshold()
    test_salt_dalam_kalimat_tetap_ketemu_lewat_windowing()
    test_target_tahap9_belum_tercapai()
    print("ok")
