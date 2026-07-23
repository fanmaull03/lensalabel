// Modul edukasi GFCF (desain EDUKASI) + pembaca artikel (desain ARTIKEL).
// Statis; konten placeholder, teks final menyusul. Toggle daftar <-> pembaca
// pakai state in-page (tanpa routing tambahan). Tidak ada aset gambar, jadi
// sampul pakai placeholder gradien, bukan image-slot desain aslinya.
import { useState } from "react";

const ARTICLES = [
  {
    title: "Apa itu diet Gluten-Free Casein-Free?",
    read: "4 menit",
    category: "Dasar-dasar GFCF",
    featured: true,
    body: "[Placeholder] Penjelasan singkat diet Gluten-Free Casein-Free: apa itu gluten dan kasein, serta mengapa sebagian orang tua anak autistik memilih diet ini. Tujuan diet ini adalah mengurangi asupan gluten dan kasein secara konsisten, bukan menghilangkan seluruh nutrisi penting anak.",
  },
  {
    title: "Membaca label komposisi dengan cermat",
    read: "3 menit",
    category: "Praktik",
    body: "[Placeholder] Tips membaca label: nama alias bahan, tulisan alergen yang dicetak tebal, dan bahan yang perlu diwaspadai.",
  },
  {
    title: "Gluten & kasein tersembunyi",
    read: "5 menit",
    category: "Praktik",
    body: "[Placeholder] Perhatikan istilah teknis seperti wheat protein, caseinate, atau whey yang sering muncul di label.",
  },
  {
    title: "Bahan yang mengandung kasein",
    read: "3 menit",
    category: "Referensi",
    body: "[Placeholder] Daftar sumber kasein umum: susu, keju, whey, dan turunannya.",
  },
];

// Glosarium istilah asing (statis, informatif). Warna mengikuti verdict.
const GLOSSARY = [
  { term: "Hydrolyzed Wheat Protein", verdict: "Hindari", color: "border-red-500 text-red-600", note: "Protein gandum yang dipecah — tetap mengandung gluten." },
  { term: "Maltodextrin", verdict: "Aman", color: "border-emerald-500 text-emerald-600", note: "Umumnya dari jagung/tapioka — biasanya bebas gluten." },
];

export default function GfcfEducationPage() {
  const [reading, setReading] = useState(null);

  if (reading) return <ArticleReader article={reading} onBack={() => setReading(null)} />;

  const [featured, ...rest] = ARTICLES;

  return (
    <div className="space-y-5 font-sans">
      <div>
        <h1 className="font-display text-2xl font-extrabold text-white">Belajar GFCF</h1>
        <p className="mt-1 text-sm text-white/65">Pahami diet dengan tenang.</p>
      </div>

      {/* featured */}
      <button
        type="button"
        onClick={() => setReading(featured)}
        className="glass block w-full overflow-hidden rounded-3xl text-left shadow-2xl transition duration-200 active:scale-[.99]"
      >
        <div className="h-32 bg-gradient-to-br from-accent-blue to-accent-purple" />
        <div className="p-5 text-white">
          <div className="text-xs font-bold uppercase tracking-wide opacity-80">Mulai di sini</div>
          <div className="mt-1 font-display text-xl font-extrabold leading-tight">{featured.title}</div>
          <div className="mt-2 text-sm text-white/70">{featured.read} baca · dasar-dasar</div>
        </div>
      </button>

      {/* daftar artikel */}
      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">Artikel</h2>
        <div className="space-y-3">
          {rest.map((a) => (
            <button
              key={a.title}
              type="button"
              onClick={() => setReading(a)}
              className="glass flex w-full items-center gap-3 rounded-2xl p-3 text-left shadow-xl transition duration-200 hover:bg-white/20 active:scale-[.99]"
            >
              <div className="h-14 w-16 flex-none rounded-xl bg-gradient-to-br from-accent-green/70 to-accent-blue/60" />
              <div className="flex-1">
                <div className="font-semibold text-white">{a.title}</div>
                <div className="text-xs text-white/60">{a.read}</div>
              </div>
              <span className="text-white/50">›</span>
            </button>
          ))}
        </div>
      </div>

      {/* glosarium */}
      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">Glosarium istilah asing</h2>
        <div className="space-y-3">
          {GLOSSARY.map((g) => (
            <div key={g.term} className={`glass-white rounded-2xl border-l-4 p-4 shadow-xl ${g.color}`}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-navy-base">{g.term}</span>
                <span className="text-xs font-bold">{g.verdict}</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500">{g.note}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Pembaca artikel (desain ARTIKEL). Sampul gradien + body placeholder.
function ArticleReader({ article, onBack }) {
  return (
    <div className="animate-fade-up overflow-hidden rounded-3xl bg-[#F7F9FC] shadow-2xl">
      <div className="relative h-40 bg-gradient-to-br from-accent-blue to-accent-purple">
        <button
          type="button"
          onClick={onBack}
          className="absolute left-4 top-4 flex h-10 w-10 items-center justify-center rounded-xl border border-white/30 bg-navy-base/30 text-white backdrop-blur transition active:scale-90"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
        </button>
        <span className="absolute bottom-4 left-5 rounded-full border border-white/35 bg-accent-blue/60 px-3 py-1 text-xs font-bold uppercase tracking-wide text-white backdrop-blur">
          {article.category}
        </span>
      </div>

      <div className="p-6">
        <h1 className="font-display text-2xl font-extrabold leading-tight text-navy-base">{article.title}</h1>
        <div className="mt-3 flex items-center gap-3">
          <div className="h-9 w-9 flex-none rounded-full bg-gradient-to-br from-accent-blue to-accent-green" />
          <div>
            <div className="text-sm font-semibold text-navy-base">Tim Gizi LensaLabel</div>
            <div className="font-mono text-xs text-slate-400">{article.read} baca · Diperbarui Jul 2026</div>
          </div>
        </div>

        <p className="mt-5 text-[15px] leading-relaxed text-slate-600">{article.body}</p>

        <div className="mt-5 rounded-2xl border-l-4 border-accent-blue bg-[#EAF0FD] p-4">
          <p className="font-display text-sm font-semibold leading-snug text-navy-base">
            "Tujuan diet ini adalah mengurangi asupan gluten dan kasein secara konsisten,
            bukan menghilangkan seluruh nutrisi penting anak."
          </p>
        </div>

        <button
          type="button"
          onClick={onBack}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-navy-base/10 bg-white py-3 font-display text-sm font-semibold text-accent-blue-link shadow-sm transition active:scale-[.98]"
        >
          ‹ Kembali ke daftar
        </button>
      </div>
    </div>
  );
}
