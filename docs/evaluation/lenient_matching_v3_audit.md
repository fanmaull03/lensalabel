# Audit perbaikan lenient anotasi v3

Catatan: dokumen ini merekam audit dan simulasi sebelum konfirmasi pengguna. Keputusan terbaru sudah diterapkan pada [review v4](calibration_v4.md): sepuluh pasangan diblokir, kode INS persis, dan relasi taksonomi lain hanya ditandai. Generalisasi 69 relasi tidak diterapkan.

Audit dilakukan terhadap 240 ingredient_id dan 1.227 varian. KB dan matcher production tidak diubah.

## Pasangan typo

| Kata A | Kata B | Status |
|---|---|---|
| almond | almonds | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| baking | caking | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| carbonate | carbonated | Usulan blokir; menunggu konfirmasi |
| casein | kasein | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| citrate | nitrate | Usulan blokir; menunggu konfirmasi |
| cokelat | coklat | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| extract | extracts | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| guaran | guarana | Usulan blokir; menunggu konfirmasi |
| instan | instant | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| kafein | kasein | Usulan blokir; menunggu konfirmasi |
| kalium | kalsium | Diotorisasi pengguna |
| nitrat | nitrit | Usulan blokir; menunggu konfirmasi |
| nitrat | sitrat | Usulan blokir; menunggu konfirmasi |
| nitrate | nitrite | Usulan blokir; menunggu konfirmasi |
| phosphate | phosphates | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| sintetik | sintetis | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| sweetened | sweetener | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |
| yoghurt | yogurt | Varian ejaan/jamak atau perubahan peran/konteks; tidak otomatis diblokir |

Natrium vs Kalium berjarak edit 3, sehingga sudah tidak lolos toleransi satu edit. Sulfat tidak ada dalam varian KB aktif; Sulfit ada. Keduanya tidak ditambahkan ke blokir tambahan secara otomatis.

Ada 162 pasangan token INS dengan edit distance 1 lintas bahan. Usulan: kode aditif harus cocok persis, bukan melalui toleransi typo. Seluruh pasangan tersedia pada sheet `pasangan_kode_INS` di workbook audit.

Identitas terpisah dirujuk oleh [PubChem: natrium nitrat](https://pubchem.ncbi.nlm.nih.gov/compound/sodium%20nitrate), [NTP: natrium nitrit](https://ntp.niehs.nih.gov/sites/default/files/ntp/htdocs/lt_rpts/tr495.pdf), [publikasi protein kasein](https://pubmed.ncbi.nlm.nih.gov/2236098/), [EFSA: kafein dan guarana](https://www.efsa.europa.eu/en/topics/topic/caffeine), dan [PubChem: guaran/guar gum](https://pubchem.ncbi.nlm.nih.gov/compound/Guar-Gum).

## Nama umum dan spesifik

69 relasi di bawah merupakan audit leksikal. Beberapa varian merupakan deskripsi, mengandung negasi, atau hubungan turunan bahan; keputusan generalisasi aturan membutuhkan konfirmasi. Kelapa/sawit sudah diotorisasi. Penerapan hanya boleh menekan nama pendek pada kemunculan yang sama; bahan pendek yang muncul terpisah tetap dipertahankan.

| Bahan umum | Bahan spesifik | Varian umum | Varian spesifik |
|---|---|---|---|
| Oat tanpa label bebas gluten (risiko kontaminasi silang) | Susu oat bersertifikat bebas gluten | Oat | Oat milk |
| Terigu / Gandum | Tepung terigu protein tinggi | Wheat flour | High-gluten wheat flour |
| Terigu / Gandum | Pati terigu | Wheat | Wheat starch |
| Terigu / Gandum | Couscous | Wheat | Couscous (wheat semolina) |
| Terigu / Gandum | Bulgur | Wheat | Bulgur wheat |
| Terigu / Gandum | Kecap asin (mengandung gandum fermentasi) | Wheat | Soy sauce (wheat-fermented) |
| Terigu / Gandum | Tepung panir (breadcrumb) berbahan gandum | Wheat | Wheat breadcrumbs |
| Terigu / Gandum | Asam folat sintetis pada produk fortifikasi gandum | Wheat | Synthetic folic acid (wheat-fortified products) |
| Terigu / Gandum | Rye (gandum hitam) | Gandum | Gandum hitam |
| Terigu / Gandum | Enzim protease dari gandum dan kedelai (bahan penolong) | Gandum | Enzim protease dari gandum dan kedelai |
| Terigu / Gandum | Tepung terigu dalam saus/kaldu instan | Terigu | Tepung terigu dalam saus |
| Kasein / Sodium kaseinat | Rennet casein | Casein | Rennet casein |
| Kasein / Sodium kaseinat | Kalsium kaseinat | Caseinate | Calcium caseinate |
| Kasein / Sodium kaseinat | Krimer non-dairy (berpotensi mengandung kaseinat) | Caseinate | Non-dairy creamer (may contain caseinate) |
| Susu sapi | Yogurt (susu sapi) | Susu sapi | Yogurt (susu sapi) |
| Susu sapi | Whey protein | Milk | Milk whey |
| Susu sapi | Susu bubuk full cream | Milk | Milk powder |
| Susu sapi | Susu kental manis | Milk | Sweetened condensed milk |
| Susu sapi | Margarin (mengandung whey/susu) | Susu | Margarin (mengandung whey/susu) |
| Susu sapi | Santan / susu kelapa | Milk | Coconut milk |
| Susu sapi | Susu beras | Milk | Rice milk |
| Susu sapi | Susu almond (tanpa perisa buatan) | Milk | Almond milk |
| Susu sapi | Susu kedelai murni | Milk | Soy milk |
| Susu sapi | Susu oat bersertifikat bebas gluten | Milk | Oat milk |
| Susu sapi | Susu skim bubuk | Milk | Skim milk powder |
| Susu sapi | Krimer susu bubuk / Padatan susu (milk solids) | Milk | Milk solids |
| Susu sapi | Lemak susu | Milk | Milk fat |
| Whey protein | Margarin (mengandung whey/susu) | Whey | Margarin (mengandung whey/susu) |
| Gula pasir murni | Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum | Gula | Gula merah |
| Kakao/cokelat murni | Coklat HT | Coklat | Coklat HT |
| Kakao/cokelat murni | Beras merah/cokelat | Cokelat | Beras cokelat |
| Perisa buatan (artificial flavor) | Susu almond (tanpa perisa buatan) | Perisa buatan | Susu almond (tanpa perisa buatan) |
| Gom arab / Selulosa bubuk / Gom guar | Natrium karboksimetil selulosa (Na-CMC) | Selulosa | Natrium karboksimetil selulosa |
| Gom arab / Selulosa bubuk / Gom guar | Metil selulosa / Karboksi metil selulosa | Selulosa | Metil selulosa |
| Minyak kelapa | Minyak sawit / Minyak kelapa sawit (termasuk minyak olein kelapa sawit, minyak goreng sawit) | Minyak kelapa | Minyak kelapa sawit |
| Malt / ekstrak malt | Malt vinegar | Malt | Malt vinegar |
| Semolina | Couscous | Semolina | Couscous (wheat semolina) |
| Susu bubuk full cream | Susu skim bubuk | Milk powder | Skim milk powder |
| Susu bubuk full cream | Krimer susu bubuk / Padatan susu (milk solids) | Susu bubuk | Krimer susu bubuk |
| Yogurt (susu sapi) | Kultur bakteri yogurt (Lactobacillus, Streptococcus thermophilus) | Yogurt | Kultur bakteri yogurt |
| Krim / Whipped cream | Susu sapi | Cream | Full cream milk |
| Krim / Whipped cream | Susu bubuk full cream | Cream | Susu bubuk full cream |
| Bumbu penyedap kaldu instan (kemungkinan HVP/gluten) | Tepung terigu dalam saus/kaldu instan | Kaldu instan | Tepung terigu dalam kaldu instan |
| Apel | Cuka apel/anggur (cider/wine vinegar) | Apel | Cuka apel |
| Jeruk | Jeruk bali (grapefruit) | Jeruk | Jeruk bali |
| Jeruk | Kuning Sunset FCF | Orange | Orange Yellow S |
| Anggur | Cuka apel/anggur (cider/wine vinegar) | Anggur | Cuka anggur |
| Almond | Susu almond (tanpa perisa buatan) | Almond | Susu almond |
| Almond | Tepung kacang almond | Almond | Almond flour |
| Tomat | Kecap tomat / saus tomat (ketchup) | Tomat | Kecap tomat |
| Paprika hijau/cabai | Bubuk cabai (chili powder) | Cabai | Bubuk cabai |
| Beras putih | Tepung beras | Beras | Tepung beras |
| Beras putih | Beras merah/cokelat | Beras | Beras merah |
| Beras putih | Susu beras | Beras | Susu beras |
| Jagung (segar) | Tepung jagung (maizena murni) | Jagung | Pati jagung |
| Jagung (segar) | Sirup glukosa / Dekstrosa / Fruktosa / Sirup fruktosa | Corn | High fructose corn syrup |
| Kentang | Ubi jalar | Potato | Sweet potato |
| Singkong / ubi kayu | Tepung tapioka | Cassava | Cassava starch |
| Sorgum | Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum | Sorgum | Gula sorgum |
| Kubis / kol | Kubis Brussel | Kubis | Kubis Brussel |
| Sukrosa | Ester asam lemak sukrosa (pengemulsi) | Sukrosa | Ester asam lemak sukrosa |
| Gula merah / Gula palem / Gula aren / Gula lontar / Gula tebu / Gula sorgum | Gula pasir murni | Cane sugar | Cane sugar (pure) |
| Ragi (baker's yeast, murni) | Ragi terhidrolisis (autolyzed yeast) | Ragi | Ragi terhidrolisis |
| Ragi (baker's yeast, murni) | Ekstrak ragi (yeast extract) | Ragi | Ekstrak ragi |
| Rumput laut | Karagenan (rumput laut) | Rumput laut | Karagenan (rumput laut) |
| Krimer susu bubuk / Padatan susu (milk solids) | Margarin (mengandung whey/susu) | Milk solids | Margarine containing whey/milk solids |
| Metil selulosa / Karboksi metil selulosa | Natrium karboksimetil selulosa (Na-CMC) | Carboxymethyl cellulose | Sodium carboxymethyl cellulose |
| Karmin / Anato (pewarna alami) | Indigotin (Indigo carmine) | Carmine | Indigo carmine |
| Karmin / Anato (pewarna alami) | Ponceau 4R | Cochineal | Cochineal Red A |

## Dampak simulasi

| Cakupan | Kandidat otomatis tersisa | Hilang dari 50 | Y yang terfilter | N yang terfilter | Kosong terfilter | Kandidat baru |
|---|---:|---:|---:|---:|---:|---:|
| Kalium/Kalsium + batas frasa + kelapa/sawit | 29 | 21 | 5 | 15 | 1 | 0 |
| Simulasi tambahan pasangan + kode persis + generalisasi nama spesifik | 17 | 33 | 13 | 19 | 1 | 0 |

File v2 yang tersedia memuat 30 Y, 19 N, dan 1 keputusan kosong, bukan 27 Y/23 N. Sumber keputusan sedang dimintakan konfirmasi.

Keputusan Y dipertahankan utuh pada sheet disetujui_manual_v2, termasuk Y yang tidak lagi ditemukan oleh aturan otomatis. Hilangnya kandidat otomatis tidak berarti membatalkan keputusan manusia. Tidak ada merge GT final pada tahap ini.

Preview cakupan yang sudah diotorisasi tersedia di [calibration_review_v3_preview.xlsx](../../evaluation/results/calibration_review_v3_preview.xlsx). File ini belum merupakan v3 final; aturan tambahan belum diterapkan. Dari 21 baris yang hilang, 5 berkeputusan Y, 15 N, dan 1 kosong. Seluruh 30 keputusan Y sumber tersedia tetap tercatat.

24 tes anotasi dan kontinuitas keputusan lulus. Hash 11 file yang dilindungi serta ukuran dan waktu modifikasi 200 foto tetap sama dengan keadaan awal pekerjaan ini. Strict GT tetap 362 anotasi untuk 40 foto.
