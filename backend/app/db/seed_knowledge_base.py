"""
Seed data knowledge base LensaLabel.

PENTING: 68 bahan di bawah ini adalah "Usulan Peneliti" dari
Lembar_Validasi_KnowledgeBase_BahanMakanan_v2, BELUM ditandatangani atau
dicentang oleh pakar medis/gizi anak (kolom Setuju dan Revisi Kategori di
lembar itu masih kosong). Semua baris di-insert dengan is_validated=False.

Setelah lembar validasi kembali dari pakar:
1. Untuk bahan yang dicentang Setuju, cukup ubah is_validated jadi True.
2. Untuk bahan yang direvisi, update kolom category di tabel ingredients
   sesuai Revisi Kategori, lalu is_validated jadi True.
3. Insert satu baris ExpertValidation per bahan untuk catatan audit trail
   (validator_name, is_agreed, revised_category, expert_notes).

Cara pakai (dari folder backend/, dengan .env sudah diisi DATABASE_URL):
  python -m app.db.seed_knowledge_base
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Base, Ingredient, IngredientSynonym, SafetyCategory

AMAN = SafetyCategory.AMAN
PERHATIAN = SafetyCategory.PERHATIAN
HINDARI = SafetyCategory.HINDARI

# (standard_name, [synonyms/kode aditif], category, justifikasi_ringkas)
DRAFT_INGREDIENTS = [
    ("Tepung terigu", ["Wheat flour", "Wheat", "Gandum", "Terigu", "Pati gandum"], HINDARI, "Sumber gluten utama"),
    ("Gluten", ["Wheat gluten", "vital wheat gluten"], HINDARI, "Protein gluten murni, inti pantangan diet GFCF"),
    ("Barley", ["Jelai", "malt"], HINDARI, "Turunan gluten dari jelai"),
    ("Hydrolyzed wheat protein", ["Protein gandum terhidrolisis", "HWP"], HINDARI, "Turunan gluten, penamaan sering menyamarkan asal gandum"),
    ("Oat", ["Havermut", "oatmeal", "Oats"], PERHATIAN, "Bebas gluten alami, namun rawan kontaminasi silang saat produksi"),
    ("Kasein", ["Casein", "sodium caseinate", "Caseinate", "Kaseinat"], HINDARI, "Protein susu utama, inti pantangan diet GFCF"),
    ("Susu sapi", ["Whole milk", "full cream milk", "Milk", "Susu", "Milk powder", "Susu bubuk"], HINDARI, "Sumber utama kasein"),
    ("Keju", ["Cheese", "Cheese powder", "Bubuk keju"], HINDARI, "Olahan susu, kandungan kasein tinggi"),
    ("Whey", ["Whey protein", "milk whey"], HINDARI, "Turunan protein susu"),
    ("Tartrazin", ["E102", "Yellow 5"], HINDARI, "Pewarna azo, terkait perubahan perilaku pada anak sensitif"),
    ("Sunset Yellow", ["E110", "Orange Yellow S"], HINDARI, "Pewarna azo, termasuk kelompok yang diteliti terkait hiperaktivitas"),
    ("Karmosin", ["E122", "Azorubine"], HINDARI, "Pewarna azo sintetis"),
    ("Ponceau 4R", ["E124", "Cochineal Red A"], HINDARI, "Pewarna azo sintetis"),
    ("Eritrosin", ["E127", "Red 3"], HINDARI, "Pewarna sintetis"),
    ("Biru Berlian", ["E133", "Brilliant Blue FCF"], PERHATIAN, "Pewarna sintetis, bukti keterkaitan perilaku lebih terbatas"),
    ("Hijau FCF", ["E143", "Fast Green FCF"], PERHATIAN, "Pewarna sintetis, bukti keterkaitan perilaku lebih terbatas"),
    ("Titanium dioksida", ["E171", "Titanium dioxide"], PERHATIAN, "Pewarna putih, menjadi sorotan regulasi di sejumlah negara"),
    ("Natrium Benzoat", ["E211", "Sodium benzoate"], PERHATIAN, "Pengawet, terkait hiperaktivitas terutama bila dikombinasi pewarna sintetis"),
    ("Kalium Benzoat", ["E212", "Potassium benzoate"], PERHATIAN, "Pengawet golongan benzoat"),
    ("Sulfit", ["E220-228", "Sulfur dioxide dan turunannya"], PERHATIAN, "Pengawet, berisiko memicu reaksi alergi/asma pada anak sensitif"),
    ("Natrium Nitrit", ["E250", "Sodium nitrite"], PERHATIAN, "Pengawet daging olahan, perlu dibatasi"),
    ("BHA", ["E320", "Butylated hydroxyanisole"], PERHATIAN, "Antioksidan sintetis, perlu dibatasi"),
    ("BHT", ["E321", "Butylated hydroxytoluene"], PERHATIAN, "Antioksidan sintetis, perlu dibatasi"),
    ("MSG", ["E621", "Monosodium glutamate", "vetsin", "Mononatrium glutamat"], PERHATIAN, "Penguat rasa, sebagian literatur mencatat sensitivitas perilaku"),
    ("Dinatrium Guanilat", ["E627", "Disodium guanylate"], PERHATIAN, "Penguat rasa, umumnya dipakai bersama MSG"),
    ("Dinatrium Inosinat", ["E631", "Disodium inosinate"], PERHATIAN, "Penguat rasa, umumnya dipakai bersama MSG"),
    ("Aspartam", ["E951", "Aspartame", "Equal"], PERHATIAN, "Pemanis buatan, bukti campuran terkait perilaku"),
    ("Sakarin", ["E954", "Saccharin", "sodium saccharin"], PERHATIAN, "Pemanis buatan"),
    ("Siklamat", ["E952", "Sodium cyclamate"], PERHATIAN, "Pemanis buatan"),
    ("Sukralosa", ["E955", "Sucralose", "Splenda"], PERHATIAN, "Pemanis buatan"),
    ("Gula pasir", ["Sukrosa", "sucrose", "sugar", "Gula"], PERHATIAN, "Gula sederhana, asupan berlebih dikaitkan gangguan perilaku"),
    ("Fruktosa tinggi", ["High fructose corn syrup", "HFCS"], PERHATIAN, "Pemanis olahan, asupan berlebih perlu dibatasi"),
    ("Kedelai", ["Soy", "soya", "Soybean"], PERHATIAN, "Sebagian anak ASD melaporkan sensitivitas terhadap kedelai"),
    ("Cokelat", ["Cocoa", "cacao", "Coklat", "Chocolate"], PERHATIAN, "Mengandung senyawa stimulan ringan"),
    ("Perisa buatan", ["Artificial flavour", "artificial flavoring", "Perisa sintetik", "Synthetic flavour"], PERHATIAN, "Komposisi tidak selalu transparan, perlu kehati-hatian"),
    ("Asam askorbat", ["E300", "Ascorbic acid", "vitamin C"], AMAN, "Vitamin alami, umum dianggap aman"),
    ("Natrium askorbat", ["E301", "Sodium ascorbate"], AMAN, "Bentuk garam vitamin C, umum dianggap aman"),
    ("Tokoferol", ["E306", "Tocopherol", "vitamin E"], AMAN, "Antioksidan alami, umum dianggap aman"),
    ("Beta karoten", ["E160a", "Beta carotene"], AMAN, "Pewarna alami dari sumber nabati"),
    ("Asam fumarat", ["E297", "Fumaric acid"], AMAN, "Asam pengatur keasaman, umum dianggap aman"),
    ("Pektin", ["E440", "Pectin", "apple pectin"], AMAN, "Serat alami dari buah"),
    ("Agar-agar", ["E406", "Agar"], AMAN, "Bahan pengental alami dari rumput laut"),
    ("Karagenan", ["E407", "Carrageenan"], PERHATIAN, "Pengental dari rumput laut, sebagian studi catat iritasi saluran cerna"),
    ("Guar gum", ["E412", "Guaran"], AMAN, "Pengental alami dari kacang guar"),
    ("Xanthan gum", ["E415"], AMAN, "Pengental hasil fermentasi, umum dianggap aman"),
    ("Akasia gum", ["E414", "Acacia gum", "gum arabic"], AMAN, "Pengental alami dari getah akasia"),
    ("Gelatin", ["E441", "Gelatine"], AMAN, "Bukan turunan gluten/kasein, perlu verifikasi sumber hewani"),
    ("Selulosa", ["E460", "Cellulose"], AMAN, "Serat nabati, umum dianggap aman"),
    ("Lesitin", ["E322", "Lecithin", "sunflower lecithin", "Soy lecithin", "Lesitin kedelai"], AMAN, "Emulsifier nabati, umumnya dari kedelai/bunga matahari"),
    ("Gliserol", ["E422", "Glycerol", "glycerine"], AMAN, "Humektan, umum dianggap aman"),
    ("Mono dan digliserida", ["E471"], AMAN, "Emulsifier, perlu verifikasi sumber nabati/hewani"),
    ("Asam sitrat", ["E330", "Citric acid"], AMAN, "Asam alami dari buah sitrus"),
    ("Natrium sitrat", ["E331", "Sodium citrate"], AMAN, "Garam asam sitrat, umum dianggap aman"),
    ("Kalium sitrat", ["E332", "Potassium citrate"], AMAN, "Garam asam sitrat, umum dianggap aman"),
    ("Asam laktat", ["E270", "Lactic acid"], AMAN, "Umumnya hasil fermentasi bakteri, bukan dari susu, perlu verifikasi sumber"),
    ("Asam malat", ["E296", "Malic acid"], AMAN, "Asam alami dari buah"),
    ("Natrium klorida", ["Sodium chloride", "garam dapur", "Salt", "Garam"], AMAN, "Garam dapur, umum dianggap aman"),
    ("Kalsium karbonat", ["E170", "Calcium carbonate"], AMAN, "Mineral, umum dianggap aman"),
    ("Kalsium fosfat", ["E341", "Calcium phosphate"], AMAN, "Mineral, umum dianggap aman"),
    ("Kalium klorida", ["E508", "Potassium chloride"], AMAN, "Mineral, umum dianggap aman"),
    ("Tepung beras", ["Rice flour"], AMAN, "Alternatif tepung bebas gluten"),
    ("Tepung tapioka", ["Tapioca starch", "cassava starch", "Tapioka"], AMAN, "Alternatif tepung bebas gluten"),
    ("Tepung sagu", ["Sago flour", "sago starch"], AMAN, "Alternatif tepung bebas gluten"),
    ("Tepung jagung", ["Corn flour", "corn starch", "maizena", "Pati jagung"], AMAN, "Alternatif tepung bebas gluten"),
    ("Minyak kelapa", ["Coconut oil"], AMAN, "Minyak nabati, bebas gluten/kasein"),
    ("Minyak zaitun", ["Olive oil"], AMAN, "Minyak nabati, bebas gluten/kasein"),
    ("Minyak jagung", ["Corn oil"], AMAN, "Minyak nabati, bebas gluten/kasein"),
    ("Minyak bunga matahari", ["Sunflower oil"], AMAN, "Minyak nabati, bebas gluten/kasein"),
]


def seed() -> None:
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)

    inserted = 0
    with Session(engine) as session:
        for standard_name, synonyms, category, justification in DRAFT_INGREDIENTS:
            already_exists = (
                session.query(Ingredient).filter_by(standard_name=standard_name).first()
            )
            if already_exists:
                continue

            ingredient = Ingredient(
                standard_name=standard_name,
                category=category,
                justification=justification,
                is_validated=False,
            )
            for syn in synonyms:
                ingredient.synonyms.append(IngredientSynonym(synonym=syn))

            session.add(ingredient)
            inserted += 1

        session.commit()

    print(f"Selesai. {inserted} bahan draft baru berhasil di-seed (is_validated=False).")


if __name__ == "__main__":
    seed()
