// Baris satu bahan hasil identifikasi: kartu putih buram + pill status berwarna
// (mengikuti mockup "Rincian Bahan"). Warna pill adalah functional color coding
// per kategori — jangan diubah. Kelas ditulis literal per kategori supaya tidak
// ikut terbuang saat purge Tailwind. Diekspor agar Detail Bahan pakai warna sama.
export const CATEGORY_STYLES = {
  aman: { pill: "bg-emerald-600", label: "Aman", accent: "border-l-emerald-500" },
  perhatian: { pill: "bg-amber-500", label: "Perhatian", accent: "border-l-amber-400" },
  hindari: { pill: "bg-red-600", label: "Hindari", accent: "border-l-red-500" },
  tidak_dikenali: { pill: "bg-slate-500", label: "?", accent: "border-l-slate-400" },
};

export default function IngredientBadge({ name, category, detail, onClick }) {
  const style = CATEGORY_STYLES[category] ?? CATEGORY_STYLES.tidak_dikenali;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={`glass-white flex w-full items-center gap-3 rounded-xl border-l-4 px-4 py-3 text-left text-sm shadow-md transition duration-200 hover:bg-white active:scale-[.99] ${style.accent}`}
      >
        <div className="flex-1">
          <span className="font-semibold text-navy-base">{name}</span>
          {detail && <span className="ml-2 text-xs text-slate-500">{detail}</span>}
        </div>
        <span className={`flex-none rounded-full px-3 py-1 text-xs font-bold text-white ${style.pill}`}>
          {style.label}
        </span>
      </button>
    </li>
  );
}
