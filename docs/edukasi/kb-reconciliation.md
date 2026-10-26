# Rekonsiliasi kategori KB untuk draf Edukasi

Audit baca saja, 24 Oktober 2026. Perbandingan memakai `old_numbers` pada KB v2 sebagai penghubung ke kolom `number` pada berkas seed. Hubungan ini bisa melibatkan pemecahan/penamaan ulang entri; perubahan kategori adalah temuan data, bukan usulan mengubah data.

- Seed file `backend/app/db/knowledge_base_gfcf.json`: **240** entri; `expert_validated: false`.
- KB v2 `evaluation/results/kb_v2_phase2/kb_v2_review.json` pada working tree utama: **259** entri; status `v2_phase2_review_only`.
- **70** hubungan lama-ke-v2 berubah kategori, mencakup **69** nomor lama; **22** entri v2 tidak mempunyai nomor lama. Daftar perubahan lengkap ada di bawah.
- Pemeriksaan runtime terpisah pada 24 Oktober 2026 menemukan 259 bahan, 1.030 sinonim, dan 264 validasi di database lokal. Kategori 12 istilah yang dikembalikan aplikasi cocok dengan KB v2; berkas seed lama bukan sumber kategori runtime saat pemeriksaan tersebut.

## Dua belas istilah glosarium

| Istilah | ID v2 | Kategori seed file | Kategori KB v2 | Tindak lanjut |
| --- | --- | --- | --- | --- |
| Hydrolyzed Wheat Protein | `v2-new-007` | Tidak ada entri lama terhubung | **hindari** | Entri baru; belum ada di seed lama |
| Maltodextrin | `v2-036` | 36: perhatian | **aman** | Berbeda dari seed lama; runtime mengikuti v2 |
| Malt extract | `v2-005` | 5: hindari | **hindari** | Sama |
| Modified starch | `v2-033` | 33: perhatian | **perhatian** | Sama |
| Dextrin | `v2-037` | 37: perhatian | **perhatian** | Sama |
| Sodium caseinate | `v2-022` | 22: hindari | **hindari** | Sama |
| Whey protein | `v2-021` | 21: hindari | **hindari** | Sama |
| Lactalbumin | `v2-026` | 26: hindari | **hindari** | Sama |
| Non-dairy creamer | `v2-029` | 29: perhatian | **perhatian** | Sama |
| Soy sauce | `v2-012` | 12: perhatian | **perhatian** | Sama |
| Oat tanpa label | `v2-014` | 14: perhatian | **hindari** | Berbeda dari seed lama; runtime mengikuti v2 |
| Lactose | `v2-025` | 25: perhatian | **hindari** | Berbeda dari seed lama; runtime mengikuti v2; alasan kategori [BUTUH VERIFIKASI AHLI] |

## Seluruh hubungan kategori yang berubah

| No. lama | Nama seed | Kategori seed | ID v2 | Nama KB v2 | Kategori v2 |
| ---: | --- | --- | --- | --- | --- |
| 11 | Tepung terigu dalam saus/kaldu instan | perhatian | `v2-001` | Terigu / Gandum | **hindari** |
| 14 | Oat tanpa label bebas gluten (risiko kontaminasi silang) | perhatian | `v2-014` | Oat tanpa label bebas gluten (risiko kontaminasi silang) | **hindari** |
| 25 | Laktosa | perhatian | `v2-025` | Laktosa | **hindari** |
| 28 | Margarin (mengandung whey/susu) | perhatian | `v2-028a` | Margarin mengandung susu/whey | **hindari** |
| 34 | Pewarna karamel | perhatian | `v2-034` | Pewarna karamel | **aman** |
| 36 | Maltodekstrin (perlu cek sumber pati) | perhatian | `v2-036` | Maltodekstrin (perlu cek sumber pati) | **aman** |
| 38 | Lesitin (kedelai umumnya aman, cek sumber) | perhatian | `v2-038` | Lesitin (kedelai umumnya aman, cek sumber) | **aman** |
| 39 | Mono- dan digliserida asam lemak | perhatian | `v2-039` | Mono- dan digliserida asam lemak | **aman** |
| 43 | Tartrazin | hindari | `v2-043` | Tartrazin | **perhatian** |
| 44 | Kuinolin Kuning | hindari | `v2-044` | Kuinolin Kuning | **perhatian** |
| 45 | Kuning Sunset FCF | hindari | `v2-045` | Kuning Sunset FCF | **perhatian** |
| 46 | Karmoisin (Azorubine) | hindari | `v2-046` | Karmoisin (Azorubine) | **perhatian** |
| 47 | Ponceau 4R | hindari | `v2-047` | Ponceau 4R | **perhatian** |
| 48 | Merah Allura AC | hindari | `v2-048` | Merah Allura AC | **perhatian** |
| 49 | Natrium Benzoat | hindari | `v2-049` | Natrium Benzoat | **perhatian** |
| 55 | Kalium Sorbat | perhatian | `v2-055` | Kalium Sorbat | **aman** |
| 56 | Natrium Nitrit | hindari | `v2-056` | Natrium Nitrit | **perhatian** |
| 57 | Natrium Nitrat | hindari | `v2-057` | Natrium Nitrat | **perhatian** |
| 59 | Monosodium Glutamat (MSG) | perhatian | `v2-059` | Monosodium Glutamat (MSG) | **aman** |
| 60 | Dinatrium Guanilat | perhatian | `v2-060` | Dinatrium Guanilat | **aman** |
| 61 | Dinatrium Inosinat | perhatian | `v2-061` | Dinatrium Inosinat | **aman** |
| 62 | Aspartam | hindari | `v2-062` | Aspartam | **perhatian** |
| 66 | Butil Hidroksianisol (BHA) | hindari | `v2-066` | Butil Hidroksianisol (BHA) | **perhatian** |
| 67 | Butil Hidroksitoluena (BHT) | hindari | `v2-067` | Butil Hidroksitoluena (BHT) | **perhatian** |
| 68 | Tersier-Butilhidrokuinon (TBHQ) | hindari | `v2-068` | Tersier-Butilhidrokuinon (TBHQ) | **perhatian** |
| 70 | Vanilin sintetis | perhatian | `v2-070` | Vanilin sintetis | **aman** |
| 72 | Asam folat sintetis pada produk fortifikasi gandum | perhatian | `v2-072` | Asam folat | **aman** |
| 73 | Apel | perhatian | `v2-073` | Apel | **aman** |
| 74 | Jeruk | perhatian | `v2-074` | Jeruk | **aman** |
| 75 | Anggur | perhatian | `v2-075` | Anggur | **aman** |
| 76 | Stroberi/berry | perhatian | `v2-076` | Stroberi/berry | **aman** |
| 77 | Ceri | perhatian | `v2-077` | Ceri | **aman** |
| 78 | Aprikot | perhatian | `v2-078` | Aprikot | **aman** |
| 79 | Plum | perhatian | `v2-079` | Plum | **aman** |
| 80 | Kismis | perhatian | `v2-080` | Kismis | **aman** |
| 81 | Prune | perhatian | `v2-081` | Prune | **aman** |
| 82 | Almond | perhatian | `v2-082` | Almond | **aman** |
| 83 | Kacang tanah | perhatian | `v2-083` | Kacang tanah | **aman** |
| 84 | Tomat | perhatian | `v2-084` | Tomat | **aman** |
| 85 | Mentimun (dengan kulit) | perhatian | `v2-085` | Mentimun (dengan kulit) | **aman** |
| 87 | Paprika hijau/cabai | perhatian | `v2-087` | Paprika hijau/cabai | **aman** |
| 88 | Kacang polong (peas) | perhatian | `v2-088` | Kacang polong (peas) | **aman** |
| 89 | Melon | perhatian | `v2-089` | Melon | **aman** |
| 90 | Blewah/nektarin/persik | perhatian | `v2-090` | Blewah/nektarin/persik | **aman** |
| 91 | Jeruk bali (grapefruit) | perhatian | `v2-091` | Jeruk bali (grapefruit) | **aman** |
| 92 | Lemon | perhatian | `v2-092` | Lemon | **aman** |
| 94 | Madu | perhatian | `v2-094` | Madu | **aman** |
| 97 | Kakao/cokelat murni | perhatian | `v2-097` | Kakao/cokelat murni | **aman** |
| 98 | Cuka apel/anggur (cider/wine vinegar) | perhatian | `v2-098` | Cuka apel/anggur (cider/wine vinegar) | **aman** |
| 100 | Cengkeh (cloves) | perhatian | `v2-100` | Cengkeh (cloves) | **aman** |
| 101 | Bubuk cabai (chili powder) | perhatian | `v2-101` | Bubuk cabai (chili powder) | **aman** |
| 102 | Minyak gandapura (oil of wintergreen) | hindari | `v2-102` | Minyak gandapura (oil of wintergreen) | **perhatian** |
| 134 | Bayam (dalam jumlah wajar) | perhatian | `v2-134` | Bayam (dalam jumlah wajar) | **aman** |
| 166 | Kacang mede (cashew) | perhatian | `v2-166` | Kacang mede (cashew) | **aman** |
| 167 | Kacang pistachio | perhatian | `v2-167` | Kacang pistachio | **aman** |
| 168 | Kacang walnut | perhatian | `v2-168` | Kacang walnut | **aman** |
| 169 | Kacang macadamia | perhatian | `v2-169` | Kacang macadamia | **aman** |
| 180 | Manitol | aman | `v2-180` | Manitol | **perhatian** |
| 190 | Gliserin (humektan, sumber bisa nabati/hewani) | perhatian | `v2-190` | Gliserin (humektan, sumber bisa nabati/hewani) | **aman** |
| 210 | Asam laktat (sumber bisa nabati/hewani) | perhatian | `v2-210` | Asam laktat (sumber bisa nabati/hewani) | **aman** |
| 217 | Ester asam lemak sukrosa (pengemulsi) | perhatian | `v2-217` | Ester asam lemak sukrosa (pengemulsi) | **aman** |
| 218 | Antibuih (sumber tidak spesifik) | perhatian | `v2-218` | Antibuih (sumber tidak spesifik) | **aman** |
| 221 | Sukralosa | aman | `v2-221` | Sukralosa | **perhatian** |
| 222 | Pemanis alami glikosida steviol (Stevia) | aman | `v2-222` | Pemanis alami glikosida steviol (Stevia) | **perhatian** |
| 223 | Sorbitol (pemanis) | aman | `v2-223` | Sorbitol (pemanis) | **perhatian** |
| 224 | Monk fruit (pemanis alami) | aman | `v2-224` | Monk fruit (pemanis alami) | **perhatian** |
| 227 | Kafein | aman | `v2-227` | Kafein | **perhatian** |
| 228 | Guarana / Ekstrak ginseng | aman | `v2-228` | Guarana / Ekstrak ginseng | **perhatian** |
| 234 | Licorice | aman | `v2-234a` | Ekstrak licorice | **perhatian** |
| 234 | Licorice | aman | `v2-234b` | Permen licorice | **perhatian** |

## Keputusan yang belum diambil

1. Alasan kategori `Laktosa` (`v2-025`) dan `Susu bebas laktosa` (`v2-new-009`) menunggu ahli gizi. Draf tidak membuat alasan pengganti.
2. Kategori glosarium sementara mengikuti KB v2 sesuai instruksi pengguna; kategori seed file berbeda untuk maltodekstrin dan oat tanpa label. Jangan menyatakan frontend/backend sudah menerapkan KB v2.
3. Jangan memperbarui seed, database, KB, backend, atau evaluasi berdasarkan tabel ini tanpa keputusan tahap berikutnya.
