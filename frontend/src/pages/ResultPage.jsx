// Halaman hasil identifikasi (desain HASIL PINDAI). Data dikirim UploadPage
// lewat router state; kalau dibuka langsung tanpa data, kembali ke upload.
// Menangani kelima verdict; verdict tidak_terbaca memakai STATE ERROR.
// Tap satu bahan -> DETAIL (data asli saja, tanpa mengarang alias/rujukan).
import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import ResultList from "../components/ResultList";
import ScanErrorState from "../components/ScanErrorState";
import { CATEGORY_STYLES } from "../components/IngredientBadge";

// 5 status verdict dari classifier (rule_based.py), masing-masing warna beda.
// className di bawah JANGAN diubah (lihat docs/notes/design_tokens.md) —
// ini pengkodean warna fungsional, sudah benar.
const VERDICT_CONFIG = {
  aman: {
    label: "Aman",
    className: "bg-emerald-600",
    iconColor: "text-emerald-600",
    icon: "check",
    description: "Tidak ditemukan bahan yang melanggar diet GFCF.",
  },
  perhatian: {
    label: "Perlu Perhatian",
    className: "bg-amber-500",
    iconColor: "text-amber-500",
    icon: "warn",
    description: "Ada bahan yang perlu dicermati. Periksa daftarnya di bawah sebelum memutuskan.",
  },
  hindari: {
    label: "Sebaiknya Hindari",
    className: "bg-red-600",
    iconColor: "text-red-600",
    icon: "cross",
    description: "Ditemukan bahan yang sebaiknya dihindari pada diet GFCF.",
  },
  perlu_verifikasi: {
    label: "Perlu Verifikasi",
    className: "bg-orange-500",
    iconColor: "text-orange-500",
    icon: "warn",
    description: "Bahan yang terbaca tergolong aman, tapi ada bagian komposisi yang tidak dikenali sistem. Periksa label aslinya.",
  },
  tidak_terbaca: {
    label: "Tidak Terbaca",
    className: "bg-slate-500",
    iconColor: "text-slate-500",
    icon: "warn",
    description: "Sistem tidak berhasil membaca komposisi apa pun dari foto ini.",
  },
};

const VERDICT_ICONS = {
  check: <polyline points="20 6 9 17 4 12" />,
  cross: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
  warn: <><line x1="12" y1="7" x2="12" y2="14" /><circle cx="12" cy="18" r="0.6" fill="currentColor" /></>,
};

// Penjelasan level-kategori (bukan per-bahan). Basis data hanya mengembalikan
// nama, skor, dan potongan teks — alias & rujukan per bahan TIDAK ada, jadi
// tidak dikarang. Teks ini generik & jujur sesuai kategori.
const CATEGORY_NOTES = {
  hindari: "Bahan ini tergolong sebaiknya dihindari pada diet GFCF karena berkaitan dengan gluten atau kasein.",
  perhatian: "Bahan ini perlu diperhatikan — bisa menyembunyikan turunan gluten/kasein atau perlu dibatasi. Periksa label aslinya.",
  aman: "Bahan ini tergolong aman untuk diet GFCF berdasarkan basis data LensaLabel.",
  tidak_dikenali: "Bahan ini tidak ditemukan di basis data. Periksa sendiri pada label asli, jangan anggap otomatis aman.",
};

export default function ResultPage() {
  const { state: result } = useLocation();
  const [selected, setSelected] = useState(null);
  if (!result) return <Navigate to="/" replace />;

  const verdict = VERDICT_CONFIG[result.verdict] ?? VERDICT_CONFIG.tidak_terbaca;
  const counts = {
    aman: (result.aman ?? []).length,
    perhatian: (result.perhatian ?? []).length,
    hindari: (result.hindari ?? []).length,
  };

  // Foto tak terbaca: pakai STATE ERROR, bukan daftar kosong yang membingungkan.
  if (result.verdict === "tidak_terbaca") {
    return (
      <div className="font-sans">
        <ScanErrorState
          title="Teksnya belum terbaca"
          message="Sistem tidak menemukan komposisi pada foto ini. Coba foto ulang dengan pencahayaan lebih terang dan pastikan tulisan komposisi terbaca jelas."
        >
          <div className="space-y-3">
            <Link
              to="/"
              className="flex w-full items-center justify-center rounded-2xl border border-white/35 bg-gradient-to-b from-accent-blue to-accent-blue-link px-6 py-3 font-display font-semibold text-white shadow-[0_10px_26px_rgba(47,111,235,0.5)] transition duration-200 hover:brightness-110 active:scale-[.98]"
            >
              Periksa Foto Lain
            </Link>
            {/* Alternatif tanpa foto: buka UploadPage langsung di mode manual. */}
            <Link
              to="/"
              state={{ manual: true }}
              className="block w-full py-1 text-center font-display text-sm font-semibold text-white/80 transition hover:text-white"
            >
              Ketik bahan secara manual
            </Link>
          </div>
        </ScanErrorState>
      </div>
    );
  }

  return (
    <div className="space-y-5 font-sans">
      {/* verdict card — warna verdict.className functional, jangan diubah */}
      <div className={`rounded-3xl border border-white/30 p-6 text-white shadow-2xl ${verdict.className}`}>
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 flex-none items-center justify-center rounded-full bg-white/90 shadow">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className={verdict.iconColor}>
              {VERDICT_ICONS[verdict.icon]}
            </svg>
          </div>
          <div>
            <p className="font-display text-xs uppercase tracking-wide opacity-80">Hasil Pemeriksaan</p>
            <p className="font-display text-2xl font-extrabold">{verdict.label}</p>
          </div>
        </div>
        <p className="mt-4 rounded-xl border border-white/20 bg-white/15 px-4 py-3 text-sm leading-relaxed">
          {verdict.description}
        </p>
      </div>

      {/* counters */}
      <div className="grid grid-cols-3 gap-3">
        <Counter value={counts.aman} label="Aman" color="text-emerald-300" tint="bg-blue-100/15" />
        <Counter value={counts.perhatian} label="Perhatian" color="text-amber-300" tint="bg-white/10" />
        <Counter value={counts.hindari} label="Hindari" color="text-red-300" tint="bg-white/15" />
      </div>

      {result.raw_text?.trim() && <OcrPanel result={result} />}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">
          Rincian Bahan
        </h2>
        <ResultList result={result} onSelect={setSelected} />
      </div>

      <Link
        to="/"
        className="block w-full rounded-2xl border border-white/35 bg-gradient-to-b from-accent-blue to-accent-blue-link px-6 py-3 text-center font-display font-semibold text-white shadow-[0_10px_26px_rgba(47,111,235,0.5)] transition duration-200 hover:brightness-110 active:scale-[.98]"
      >
        Periksa Foto Lain
      </Link>

      {selected && <DetailModal item={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Counter({ value, label, color, tint }) {
  return (
    <div className={`rounded-2xl border border-white/25 p-3 text-center backdrop-blur-xl ${tint}`}>
      <div className={`font-display text-xl font-extrabold ${color}`}>{value}</div>
      <div className="text-xs text-white/65">{label}</div>
    </div>
  );
}

// composition_text adalah rentang yang dianalisis; raw_text tetap tersedia untuk diperiksa.
function OcrPanel({ result }) {
  const composition = result.composition_text?.trim() || result.raw_text;
  const note = result.input_source === "manual"
    ? "Analisis memakai teks komposisi yang Anda masukkan."
    : result.opening_marker_found && result.closing_marker_found
      ? "Penanda komposisi dan penanda akhir ditemukan. Analisis memakai teks dari penanda komposisi hingga sebelum penanda akhir."
      : result.opening_marker_found
        ? "Penanda komposisi ditemukan. Analisis memakai teks sejak penanda komposisi."
        : "Penanda komposisi tidak ditemukan. Analisis memakai seluruh teks yang terbaca.";
  return (
    <div>
      <h2 className="mb-3 font-display text-base font-bold text-white">Teks komposisi yang dianalisis</h2>
      <div className="glass-white rounded-2xl p-4 text-sm leading-relaxed shadow-xl">
        <p className="text-slate-600">{note}</p>
        <p className="mt-4 whitespace-pre-wrap text-navy-base [overflow-wrap:anywhere]">
          {highlight(composition, result)}
        </p>
      </div>
      {result.input_source !== "manual" && (
        <details className="group mt-3 rounded-2xl bg-white/90 text-navy-base shadow-lg">
          <summary className="flex min-h-12 cursor-pointer list-none items-center px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">Lihat teks OCR lengkap</span>
            <span className="hidden group-open:inline">Sembunyikan teks OCR lengkap</span>
          </summary>
          <p className="border-t border-slate-200 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
            {highlight(result.raw_text, result)}
          </p>
        </details>
      )}
    </div>
  );
}

function highlight(text, result) {
  const terms = [
    ...(result.hindari ?? []).map((b) => ({ w: b.matched_window, cls: "bg-red-100 text-red-700 font-semibold" })),
    ...(result.perhatian ?? []).map((b) => ({ w: b.matched_window, cls: "bg-amber-100 text-amber-700 font-semibold" })),
    ...(result.aman ?? []).map((b) => ({ w: b.matched_window, cls: "bg-emerald-100 text-emerald-800 font-semibold" })),
  ].flatMap((term) => {
    if (!term.w) return [];
    return (text.toLowerCase().includes(term.w.toLowerCase()) ? [term.w] : term.w.split(", "))
      .filter(Boolean)
      .map((w) => ({ ...term, w }));
  }).sort((a, b) => b.w.length - a.w.length);
  if (terms.length === 0) return text;

  const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(${terms.map((t) => escape(t.w)).join("|")})`, "gi");
  const clsFor = (frag) => terms.find((t) => t.w.toLowerCase() === frag.toLowerCase())?.cls;
  return text.split(re).map((frag, i) => {
    const cls = clsFor(frag);
    return cls ? <mark key={i} className={`rounded px-1 ${cls}`}>{frag}</mark> : frag;
  });
}

// DETAIL (desain DETAIL) — hanya data asli: nama, badge kategori, teks terbaca,
// skor, + catatan level-kategori & disclaimer ilmiah generik. Tidak ada alias
// atau rujukan per-bahan karena backend tidak menyediakannya.
function DetailModal({ item, onClose }) {
  const style = CATEGORY_STYLES[item.category] ?? CATEGORY_STYLES.tidak_dikenali;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm sm:items-center" onClick={onClose}>
      <div
        className="w-full max-w-md animate-fade-up rounded-3xl bg-[#F7F9FC] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-display text-2xl font-extrabold text-navy-base">{item.name}</h2>
            <span className={`mt-2 inline-block rounded-full px-3 py-1 text-xs font-bold text-white ${style.pill}`}>
              {style.label}
            </span>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 transition hover:text-slate-600">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <div className="mt-4 rounded-2xl bg-white p-4 shadow-sm">
          <p className="font-display text-sm font-bold text-navy-base">Kenapa status ini?</p>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">{CATEGORY_NOTES[item.category]}</p>

          {item.matched && (
            <>
              <p className="mt-4 font-display text-sm font-bold text-navy-base">Terbaca sebagai</p>
              <p className="mt-1 font-mono text-sm text-slate-700">"{item.matched}"</p>
            </>
          )}
          {item.terdekat && (
            <>
              <p className="mt-4 font-display text-sm font-bold text-navy-base">Kemiripan terdekat</p>
              <p className="mt-1 font-mono text-sm text-slate-700">{item.terdekat}</p>
            </>
          )}
          {typeof item.score === "number" && (
            <p className="mt-3 font-mono text-xs text-slate-400">Skor kecocokan: {item.score.toFixed(2)}</p>
          )}
        </div>

        <div className="mt-4 rounded-2xl border border-accent-blue/20 bg-[#EAF0FD] p-4">
          <p className="font-display text-xs font-bold text-accent-blue-link">Catatan ilmiah</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            Diet bebas gluten-kasein masih diteliti; manfaatnya bervariasi antar anak.
            Konsultasikan dengan dokter atau ahli gizi sebelum menerapkannya.
          </p>
        </div>
      </div>
    </div>
  );
}
