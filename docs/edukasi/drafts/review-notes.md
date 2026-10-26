# Catatan review konten edukasi

Status: konten telah diintegrasikan ke frontend dan sedang menunggu tinjauan ahli gizi. KB, seed, backend, evaluasi, dan berkas beku tidak diubah. Tidak ada data tingkat studi yang diambil dari Tabel 1 Yu et al. karena nama penulisnya tidak cocok dengan daftar pustaka.

## Cakupan dan panjang

| Berkas | Kata Tahap 2 awal | Kata revisi perkiraan | Perubahan perkiraan | Sumber unik pada isi |
| --- | ---: | ---: | ---: | ---: |
| `01-apa-itu-diet-gfcf.md` | 735 | 729 | −1% | 10 |
| `02-membaca-label-komposisi.md` | 593 | 365 | −38% | 7 |
| `03-gluten-kasein-tersembunyi.md` | 974 | 713 | −27% | 9 |
| `04-bahan-yang-mengandung-kasein.md` | 573 | 423 | −26% | 6 |
| `glossary.md` | 12 istilah | 12 kartu pendek | dipadatkan | 0 penanda pada kartu |

Hitungan kata memakai paragraf isi dan kutipan sorotan, tanpa judul, metadata, subjudul, penanda sumber, atau referensi. Durasi baca di frontend dihitung dari kata pada blok `body` dengan 200 kata per menit. Sumber eksternal dipakai untuk klaim pangan/klinis; fungsi LensaLabel tidak diberi penanda sumber eksternal dan kategori KB hanya menyebut ID entri. Tidak ada klaim berlabel `[BUTUH SUMBER]` yang sengaja dibiarkan dalam draf.

## Perubahan revisi dan audit redaksi

| Berkas | Perubahan utama |
| --- | --- |
| `01-apa-itu-diet-gfcf.md` | Pembuka sesuai definisi GFCF; uraian Hyman mengikuti abstrak; hipotesis peptida opioid diberi batas; paragraf gizi memakai Quan dan Hyman. |
| `02-membaca-label-komposisi.md` | Pengulangan langkah membaca label dipangkas; Pasal 50 BPOM diparafrasekan bersama arti praktis pengecualian informasi alergen. |
| `03-gluten-kasein-tersembunyi.md` | Contoh dan batas aplikasi yang berulang dipangkas; contoh aturan Kanada dan uraian fermentasi FDA dihapus; kategori bahan dipisahkan dari sumber pangan. |
| `04-bahan-yang-mengandung-kasein.md` | Aturan aplikasi untuk whey/laktalbumin disederhanakan; alasan kategori laktosa menunggu ahli gizi. |
| `glossary.md` | Dua belas kartu ringkas tanpa penanda sumber; kartu laktosa terdiri dari dua kalimat pendek sesuai redaksi yang diminta. |
| `sources.md` | Matriks sumber diselaraskan dengan sitasi yang benar-benar dipakai; S05 tidak lagi menjadi dasar definisi gluten; S09 memakai titik dua pada judul. |
| `kb-reconciliation.md` | Audit baca saja terhadap 240 entri seed dan 259 entri KB v2, termasuk 70 hubungan kategori berbeda. |

Pencarian pada empat artikel dan glosarium, di luar bagian Referensi, tidak menemukan bentuk `menjanjikan`, `tidak efektif`, `menyembuhkan`, `mengobati`, `pasti memperbaiki`, `terbukti menyembuhkan`, atau `terapi untuk autisme`. Semua ID sitasi pada isi memiliki entri Referensi dan setiap daftar Referensi diurutkan menurut ID.

## Kutipan pemeriksaan koreksi

- [Quan et al. 2022, bagian *Safety issues*](https://pmc.ncbi.nlm.nih.gov/articles/PMC8990762/): “the intervention group did not differ from the control group in terms of side effects.” Bagian ini menyebut **empat studi** yang melaporkan keamanan. Kalimat artikel 1 dibatasi pada empat studi tersebut.
- [PerBPOM 31/2018 Pasal 50 ayat (1)](https://peraturan.bpk.go.id/Download/214323/Peraturan%20BPOM%20Nomor%2031%20Tahun%202018.pdf): “Dikecualikan dari ketentuan sebagaimana dimaksud dalam Pasal 49”. Ayat (2) huruf a memuat “produk serealia antara lain sirup glukosa (termasuk dekstrosa), maltodekstrin”.
- [PerBPOM 20/2021 Pasal I angka 12–13](https://peraturan.bpk.go.id/Download/175158/Peraturan%20BPOM%20Nomor%2020%20Tahun%202021.pdf): “Ketentuan ayat (3) Pasal 49 diubah” dan “Ketentuan Pasal 51 diubah”. **Pasal 50 tidak diubah** oleh peraturan ini. Pasal 49 ayat (3) tetap menyebut gandum dalam kelompok serealia mengandung gluten. Karena pengecualian Pasal 50 dapat berlaku pada produk serealia yang dimurnikan lebih lanjut, ketiadaan kata gandum pada informasi alergen saja tidak memastikan asal maltodekstrin; ini inferensi pembacaan kedua pasal, bukan pernyataan kadar gluten produk.
- Metadata KB v2 menyebut `Lembar_Validasi_KB_GFCF_draft_validasi.docx` sebagai dokumen sumber, tetapi berkas itu tidak ditemukan dalam checkout yang dapat dibaca. Legenda glosarium memakai definisi operasional ahli yang telah diberikan pengguna dalam brief awal; cocokkan kembali dengan lembar validasi sebelum publikasi.

## Konflik dan batas penerapan KB

- Berkas KB v2 (`evaluation/results/kb_v2_phase2/kb_v2_review.json`) memuat 259 entri dan metadata historis `v2_phase2_review_only`; berkas seed lama memuat 240 entri. Audit API dan PostgreSQL lokal pada 24 Oktober 2026 menemukan 259 bahan, 1.030 sinonim, dan 264 validasi, dengan hash varian KB v2 `4c6cbe97400c2947910f6c497f2d0170bf3295c94da7c64e8ea349ca05305c9e`. Dua belas istilah glosarium menghasilkan kategori runtime yang sama dengan KB v2. Rincian perbandingan seed lama dan KB v2 ada di `docs/edukasi/kb-reconciliation.md`.
- KB v2 mengategorikan laktosa sebagai Hindari. Sumber pangan menjelaskan laktosa adalah gula susu, bukan kasein. Draf mempertahankan kategori internal sekaligus menjelaskan identitas zat secara akurat. Ahli gizi perlu menilai apakah penjelasan ini cukup jelas bagi orang tua dan apakah kategori operasional perlu catatan tambahan.
- KB v2 mengategorikan whey sebagai Hindari. Whey adalah protein susu yang berbeda dari kasein. Draf menyebut kategori aplikasi berdasarkan `v2-021`, tanpa menjadikan whey sinonim kasein.
- KB v2 memberi maltodekstrin kategori Aman dengan catatan periksa sumber pati. BPOM menyebut maltodekstrin sebagai contoh produk serealia yang dimurnikan lebih lanjut. Draf menekankan kategori bahan tidak memastikan seluruh produk akhir bebas gluten. Ahli gizi perlu menilai kecukupan catatan ini untuk orang tua yang membutuhkan pembatasan ketat.
- KB v2 menempatkan kecap asin yang mengandung gandum fermentasi dalam Perlu Perhatian, bukan Hindari. Draf menghindari klaim semua kecap asin mengandung gandum dan tetap mengikuti kategori KB. Keputusan kategori spesifik ini perlu ditinjau ahli.
- KB v2 menempatkan krimer non-dairy yang berpotensi mengandung kaseinat sebagai Perlu Perhatian. Draf meminta pembaca memeriksa komposisi; contoh aturan klaim Kanada tidak dimasukkan ke artikel.

## Perlu verifikasi sebelum konten diterbitkan

1. **[BUTUH VERIFIKASI MANUSIA]** Tabel dan ruang lingkup Lampiran VI Peraturan BPOM 1/2022. Draf hanya menyebut ada ketentuan klaim bebas gluten, tanpa angka ambang. Pengguna akan memeriksa sendiri.
2. Piwowarczyk 2018 (S16) dan Hyman 2016 (S17) dibaca dari abstrak/halaman penerbit karena teks penuh berbayar. Draf memakai hanya temuan yang tampil di abstrak. Keller 2021 (S15) sudah dibaca sebagai PDF penuh resmi.
3. Naskah standar asli Codex CXS 118-1979 belum berhasil dibuka; S05 adalah dokumen tinjauan resmi, bukan standar normatif. Draf tidak menulis angka Codex.
4. Ahli gizi perlu meninjau cara draf membedakan GFCF untuk keluarga anak autisme dari penanganan medis untuk celiac atau alergi susu, serta saran pemantauan gizi tanpa memberi target/dosis.
5. Atribusi “Disusun oleh peneliti LensaLabel” adalah sementara. Jangan ubah menjadi klaim ditinjau ahli gizi sebelum persetujuan beliau.

## Penerapan frontend

Empat artikel dan 12 kartu dipindahkan ke `frontend/src/data/educationContent.js`. Sitasi `[Sxx]` diubah menjadi nomor lokal per artikel sesuai urutan kemunculan pertama. Kalimat draf yang masih memuat penanda `[BUTUH VERIFIKASI MANUSIA]` atau `[BUTUH VERIFIKASI AHLI]` tidak dimasukkan ke data frontend. Ini mencakup angka batas Lampiran VI dan alasan kategori laktosa; keduanya tetap perlu diverifikasi sebelum ditambahkan. Nilai `EXPERT_REVIEWED` tetap `false` sehingga halaman menampilkan catatan tinjauan ahli gizi. Skrip `check:content` memeriksa penanda dan kata terlarang di data frontend.
