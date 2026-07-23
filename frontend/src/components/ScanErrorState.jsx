// State error "teks tidak terbaca" (desain STATE ERROR). Nada tenang, bukan
// alarm. Dipakai dua tempat: UploadPage saat backend 400/503, dan ResultPage
// saat verdict = tidak_terbaca. Tombol aksi dikirim lewat children karena beda
// per konteks.
const TIPS = [
  { icon: "sun", text: "Pastikan cahaya cukup terang, tanpa bayangan." },
  { icon: "focus", text: "Tahan ponsel hingga fokus stabil." },
  { icon: "zoom", text: "Dekatkan kamera ke tulisan komposisi." },
];

const TIP_ICONS = {
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1l2.1-2.1M17 7l2.1-2.1" /></>,
  focus: <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />,
  zoom: <><line x1="21" y1="21" x2="16.5" y2="16.5" /><circle cx="11" cy="11" r="7" /><line x1="11" y1="8" x2="11" y2="14" /><line x1="8" y1="11" x2="14" y2="11" /></>,
};

export default function ScanErrorState({ title, message, children }) {
  return (
    <div className="space-y-5">
      {/* ikon peringatan lembut */}
      <div className="flex justify-center">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border border-white/40 bg-gold/80 shadow-[0_6px_18px_rgba(0,0,0,0.3)] backdrop-blur">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round">
            <line x1="12" y1="7" x2="12" y2="14" />
            <circle cx="12" cy="18" r="0.6" fill="#fff" />
          </svg>
        </div>
      </div>

      <div className="text-center">
        <h2 className="font-display text-xl font-bold text-white">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/75">{message}</p>
      </div>

      <ul className="glass-white overflow-hidden rounded-2xl shadow-xl">
        {TIPS.map(({ icon, text }) => (
          <li key={icon} className="flex items-center gap-3 border-b border-navy-base/10 px-4 py-3 text-sm text-slate-700 last:border-b-0">
            <span className="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-slate-100 text-accent-blue-link">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {TIP_ICONS[icon]}
              </svg>
            </span>
            {text}
          </li>
        ))}
      </ul>

      {children}
    </div>
  );
}
