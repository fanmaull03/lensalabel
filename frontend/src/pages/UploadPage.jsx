// Beranda/Pindai (desain BERANDA) + kamera live full-bleed (KAMERA FULL-BLEED)
// + state loading (ROW 1.8) + state error (STATE ERROR). Alur: pilih foto ->
// POST /identify -> navigasi ke /hasil. Kalau gagal, tampilkan STATE ERROR.
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import CameraCapture from "../components/CameraCapture";
import ScanErrorState from "../components/ScanErrorState";
import { identifyManual, identifyPackage } from "../api/client";
import logo from "../assets/lensalabel_logo.png";

// Proses OCR di CPU laptop bisa 30 detik - 2 menit (sudah diprofilkan, bukan
// bug). Pesan loading berganti bertahap supaya user tahu aplikasi tidak hang.
const LOADING_MESSAGES = [
  { afterSeconds: 0, text: "Mengunggah foto..." },
  { afterSeconds: 4, text: "Membaca label kemasan..." },
  { afterSeconds: 20, text: "Masih memproses, foto dengan teks kecil butuh waktu lebih lama..." },
  { afterSeconds: 60, text: "Sedikit lagi, sedang mencocokkan bahan dengan basis data GFCF..." },
  { afterSeconds: 100, text: "Masih berjalan. Membaca label memang bisa sampai 2 menit, mohon jangan tutup halaman ini..." },
];

function loadingMessage(elapsedSeconds) {
  let current = LOADING_MESSAGES[0].text;
  for (const { afterSeconds, text } of LOADING_MESSAGES) {
    if (elapsedSeconds >= afterSeconds) current = text;
  }
  return current;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const fileRef = useRef(null);
  // ResultPage (verdict Tidak Terbaca) mengarahkan ke sini dengan state.manual.
  const [mode, setMode] = useState(location.state?.manual ? "manual" : "idle"); // idle | camera | manual
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!loading) return;
    setElapsed(0);
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  // Jalankan satu request identify (foto atau manual) dengan penanganan sama.
  async function run(promise) {
    setMode("idle");
    setError(null);
    setLoading(true);
    try {
      const result = await promise;
      navigate("/hasil", { state: result });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleFile = (file) => run(identifyPackage(file));
  const handleManual = (text) => run(identifyManual(text));

  if (mode === "camera") {
    return <CameraCapture onCapture={handleFile} onCancel={() => setMode("idle")} />;
  }

  if (mode === "manual") {
    return <ManualEntry onSubmit={handleManual} onCancel={() => setMode("idle")} />;
  }

  if (loading) return <LoadingCard elapsed={elapsed} message={loadingMessage(elapsed)} />;

  return (
    <div className="space-y-6 font-sans">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />

      {/* brand + info */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <img src={logo} alt="LensaLabel" className="h-11 w-11 flex-none object-contain drop-shadow-[0_2px_4px_rgba(0,0,0,0.3)]" />
          <div>
            <h1 className="font-display text-2xl font-extrabold text-white">
              Lensa<span className="text-accent-blue">Label</span>
            </h1>
            <p className="mt-1 text-sm font-medium text-gold">
              Lihat Jelas Komposisi, Pilih dengan Pasti.
            </p>
          </div>
        </div>
        <Link
          to="/tentang"
          title="Tentang LensaLabel"
          className="glass flex h-10 w-10 flex-none items-center justify-center rounded-full text-lg font-bold text-white transition duration-200 hover:bg-white/20 active:scale-90"
        >
          i
        </Link>
      </div>

      {error ? (
        <ScanErrorState
          title="Teksnya belum terbaca"
          message={error}
        >
          <div className="space-y-3">
            <PrimaryButton onClick={() => setMode("camera")}>Ambil Ulang Foto</PrimaryButton>
            <GlassButton onClick={() => fileRef.current?.click()}>Unggah dari Galeri</GlassButton>
            <TextLink onClick={() => setMode("manual")}>Ketik bahan secara manual</TextLink>
          </div>
        </ScanErrorState>
      ) : (
        <>
          {/* viewfinder hero */}
          <div className="glass rounded-3xl p-6 text-center shadow-2xl">
            <div className="relative mb-5 flex h-40 animate-float items-center justify-center rounded-2xl border border-white/15 bg-navy-base/30">
              <span className="absolute left-3 top-3 h-7 w-7 rounded-tl-lg border-l-[3px] border-t-[3px] border-white/90" />
              <span className="absolute right-3 top-3 h-7 w-7 rounded-tr-lg border-r-[3px] border-t-[3px] border-white/90" />
              <span className="absolute bottom-3 left-3 h-7 w-7 rounded-bl-lg border-b-[3px] border-l-[3px] border-white/90" />
              <span className="absolute bottom-3 right-3 h-7 w-7 rounded-br-lg border-b-[3px] border-r-[3px] border-white/90" />
              <div className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-gold shadow-[0_0_18px_rgba(242,185,77,0.6)]">
                <span className="h-2 w-2 rounded-full bg-gold shadow-[0_0_8px_#F2B94D]" />
              </div>
            </div>
            <p className="font-display text-base font-semibold text-white">
              Arahkan kamera ke daftar komposisi
            </p>
            <p className="mt-1 text-sm text-white/70">
              Foto bagian <span className="font-semibold text-white">komposisi</span> pada
              kemasan agar teksnya terlihat jelas di bingkai.
            </p>
          </div>

          <div className="space-y-3">
            <PrimaryButton onClick={() => setMode("camera")}>
              <CameraIcon /> Pindai Label
            </PrimaryButton>
            <GlassButton onClick={() => fileRef.current?.click()}>
              <GalleryIcon /> Unggah dari Galeri
            </GlassButton>
            <TextLink onClick={() => setMode("manual")}>Ketik bahan secara manual</TextLink>
          </div>

          <p className="text-center text-xs text-white/60">
            Tips: pastikan tulisan komposisi terlihat jelas, tidak silau, dan memenuhi
            sebagian besar foto.
          </p>
        </>
      )}
    </div>
  );
}

function PrimaryButton({ onClick, children, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/35 bg-gradient-to-b from-accent-blue to-accent-blue-link px-6 py-4 font-display text-base font-bold text-white shadow-[0_10px_26px_rgba(47,111,235,0.5)] transition duration-200 hover:brightness-110 active:scale-[.98] disabled:cursor-not-allowed disabled:border-white/10 disabled:from-white/20 disabled:to-white/20 disabled:shadow-none disabled:active:scale-100"
    >
      {children}
    </button>
  );
}

function GlassButton({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass flex w-full items-center justify-center gap-2 rounded-2xl px-6 py-3.5 font-display text-sm font-semibold text-white transition duration-200 hover:bg-white/20 active:scale-[.98]"
    >
      {children}
    </button>
  );
}

function TextLink({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full py-1 text-center font-display text-sm font-semibold text-white/80 transition hover:text-white"
    >
      {children}
    </button>
  );
}

// Ketik bahan manual (desain KETIK BAHAN MANUAL / ROW 1.7). Alternatif tanpa
// foto: user menyalin/mengetik daftar komposisi, dikirim ke /identify-manual.
function ManualEntry({ onSubmit, onCancel }) {
  const [text, setText] = useState("");
  // Pratinjau jumlah bahan: pecah per koma, buang yang kosong. Status per bahan
  // belum diketahui sebelum dikirim, jadi chip netral (tanpa warna palsu).
  const items = text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const canSubmit = items.length > 0;

  return (
    <div className="space-y-5 font-sans">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="glass flex h-9 w-9 flex-none items-center justify-center rounded-xl text-white transition active:scale-90"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
        </button>
        <h1 className="font-display text-xl font-bold text-white">Ketik Bahan</h1>
      </div>

      <p className="text-sm leading-relaxed text-white/75">
        Salin atau ketik daftar komposisi dari kemasan. Pisahkan tiap bahan dengan
        koma — LensaLabel memeriksanya satu per satu.
      </p>

      <div>
        <label className="mb-2 block font-display text-sm font-semibold text-white/75">
          Daftar komposisi
        </label>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="Tepung terigu, tepung tapioka, garam, penguat rasa, cabai bubuk…"
          className="glass w-full rounded-2xl p-4 text-sm leading-relaxed text-white placeholder-white/40 shadow-inner outline-none focus:border-white/50"
        />
      </div>

      {items.length > 0 && (
        <div>
          <div className="mb-2 font-display text-xs font-semibold uppercase tracking-wide text-white/60">
            {items.length} bahan terdeteksi
          </div>
          <div className="flex flex-wrap gap-2">
            {items.map((it, i) => (
              <span key={i} className="glass rounded-full px-3 py-1.5 text-sm text-white">
                {it}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-start gap-2.5 rounded-2xl border border-white/20 bg-gold/10 p-3.5 backdrop-blur-xl">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F2B94D" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-none">
          <circle cx="12" cy="12" r="9" /><line x1="12" y1="11" x2="12" y2="16" /><circle cx="12" cy="7.8" r="0.6" fill="#F2B94D" />
        </svg>
        <p className="text-xs leading-relaxed text-white/85">
          Ketik persis seperti tertulis di kemasan agar pencocokan lebih akurat,
          termasuk kode aditif seperti <span className="font-mono">E102</span>.
        </p>
      </div>

      <div className="space-y-3">
        <PrimaryButton disabled={!canSubmit} onClick={() => onSubmit(text)}>
          Periksa Bahan
        </PrimaryButton>
        <TextLink onClick={onCancel}>Pindai dengan kamera saja</TextLink>
      </div>
    </div>
  );
}

const CameraIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="7" width="18" height="13" rx="3" />
    <circle cx="12" cy="13.5" r="3.4" />
    <path d="M8.5 7l1.2-2h4.6L15.5 7" />
  </svg>
);
const GalleryIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <circle cx="8.5" cy="9" r="1.6" />
    <path d="M4 18l5-5 4 4 3-3 4 4" />
  </svg>
);

// Langkah proses. Backend satu request panjang tanpa callback per-tahap, jadi
// kemajuan diperkirakan dari waktu berjalan (ambang disamakan dengan pesan
// loading: mencocokkan ~60s). Step TERAKHIR tidak pernah ditandai selesai —
// selalu "active" sampai request rampung & halaman berpindah ke hasil, supaya
// tidak mengklaim selesai padahal masih proses.
const STEPS = ["Foto diterima", "Membaca teks (OCR)…", "Mencocokkan ke basis data", "Menyiapkan hasil"];

function stepStatuses(elapsed) {
  const active = elapsed < 60 ? 1 : elapsed < 100 ? 2 : 3;
  return STEPS.map((_, i) => (i < active ? "done" : i === active ? "active" : "pending"));
}

// State loading (ROW 1.8): kartu label disapu garis pindai, aperture berputar,
// langkah berjalan urut, bar shimmer indeterminate.
function LoadingCard({ elapsed, message }) {
  const statuses = stepStatuses(elapsed);
  return (
    <div className="glass rounded-3xl p-6 text-center shadow-2xl">
      {/* kartu label difoto disapu garis pindai */}
      <div className="relative mx-auto h-64 w-52 animate-float overflow-hidden rounded-2xl border border-white/25 shadow-2xl">
        <div className="absolute inset-0 bg-[repeating-linear-gradient(180deg,#fff_0_3px,#f1f1ea_3px_22px)]" />
        <pre className="absolute inset-0 whitespace-pre-wrap p-5 text-left font-mono text-[11px] leading-[2] text-slate-400">
KOMPOSISI:
TEPUNG TERIGU,
TEPUNG TAPIOKA,
GARAM, PENGUAT
RASA, CABAI BUBUK,
PERISA AYAM GORENG.
        </pre>
        <span className="absolute left-3 top-3 h-5 w-5 rounded-tl border-l-[3px] border-t-[3px] border-gold" />
        <span className="absolute right-3 top-3 h-5 w-5 rounded-tr border-r-[3px] border-t-[3px] border-gold" />
        <span className="absolute bottom-3 left-3 h-5 w-5 rounded-bl border-b-[3px] border-l-[3px] border-gold" />
        <span className="absolute bottom-3 right-3 h-5 w-5 rounded-br border-b-[3px] border-r-[3px] border-gold" />
        <div className="absolute inset-x-0 top-0 h-9 animate-scan bg-gradient-to-b from-transparent to-accent-blue/70 shadow-[0_4px_12px_rgba(90,150,255,0.6)]" />
      </div>

      {/* aperture berputar */}
      <div className="mt-7 flex justify-center">
        <div className="relative h-16 w-16">
          <div className="absolute inset-0 animate-spin rounded-full border-[3px] border-white/15 border-r-accent-blue border-t-[#9bc0ff]" />
          <div className="absolute left-1/2 top-1/2 animate-pulse-ring text-gold drop-shadow-[0_0_8px_rgba(242,185,77,0.9)]">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7" />
              <line x1="21" y1="21" x2="16.5" y2="16.5" />
            </svg>
          </div>
        </div>
      </div>

      <p className="mt-5 font-display text-lg font-extrabold text-white">Sedang menganalisis…</p>
      <p className="mt-1 text-sm text-white/70">{message}</p>

      <div className="mx-auto mt-5 max-w-[15rem] space-y-3 text-left">
        {STEPS.map((label, i) => (
          <Step key={label} state={statuses[i]} label={label} />
        ))}
      </div>

      {/* bar shimmer indeterminate — bukan persentase palsu */}
      <div className="mt-6 h-2 overflow-hidden rounded-full bg-white/15">
        <div className="h-full w-1/2 animate-shimmer rounded-full bg-[linear-gradient(90deg,#2F6FEB,#9bc0ff_50%,#2F6FEB)] bg-[length:200px_100%]" />
      </div>
      <p className="mt-3 font-mono text-xs text-white/60">{elapsed} detik berjalan</p>
    </div>
  );
}

function Step({ state, label }) {
  const dot =
    state === "done" ? (
      <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent-green text-xs font-bold text-white">✓</span>
    ) : state === "active" ? (
      <span className="h-6 w-6 flex-none animate-spin rounded-full border-2 border-white/80 border-t-transparent" />
    ) : (
      <span className="h-6 w-6 flex-none rounded-full border-2 border-white/30" />
    );
  return (
    <div className={`flex items-center gap-3 ${state === "active" ? "animate-fade-blink" : ""} ${state === "pending" ? "opacity-50" : ""}`}>
      {dot}
      <span className="text-sm font-medium text-white">{label}</span>
    </div>
  );
}
