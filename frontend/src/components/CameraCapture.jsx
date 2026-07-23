// Layar kamera live full-bleed (desain KAMERA FULL-BLEED). Pakai MediaDevices
// bawaan browser — tanpa library. Shutter menangkap satu frame video ke canvas
// lalu mengirimnya sebagai File JPEG, bentuk yang sama seperti input file, jadi
// pipeline /identify tidak berubah.
import { useEffect, useRef, useState } from "react";
import logo from "../assets/lensalabel_logo.png";

export default function CameraCapture({ onCapture, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [facing, setFacing] = useState("environment");
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    let active = true;
    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: facing },
          audio: false,
        });
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch {
        // Izin ditolak / tidak ada kamera: tetap buka overlay, tawarkan galeri.
        if (active) setDenied(true);
      }
    }
    start();
    // Stop track saat ganti kamera / overlay ditutup — jangan biarkan lampu
    // kamera menyala setelah keluar.
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [facing]);

  function shoot() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => blob && onCapture(new File([blob], "kamera.jpg", { type: "image/jpeg" })),
      "image/jpeg",
      0.92,
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black">
      {/* feed kamera */}
      {!denied && (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_42%,transparent_38%,rgba(0,0,0,0.55))]" />

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onCapture(file);
          e.target.value = "";
        }}
      />

      <div className="relative flex h-full flex-col">
        {/* hint bar atas */}
        <div className="mx-4 mt-4 flex items-center gap-2 rounded-2xl border border-white/25 bg-navy-base/40 px-4 py-3 text-white backdrop-blur-xl">
          <img src={logo} alt="" className="h-6 w-6 flex-none object-contain" />
          <p className="text-sm leading-snug">
            Posisikan <b>daftar komposisi</b> di dalam bingkai
          </p>
          <button
            type="button"
            onClick={onCancel}
            className="ml-auto text-sm text-white/70 transition hover:text-white"
          >
            Tutup
          </button>
        </div>

        {/* viewfinder tengah */}
        <div className="flex flex-1 items-center justify-center p-6">
          {denied ? (
            <div className="max-w-xs rounded-2xl border border-white/25 bg-navy-base/50 p-6 text-center text-white backdrop-blur-xl">
              <p className="font-display text-lg font-bold">Kamera tidak bisa diakses</p>
              <p className="mt-2 text-sm text-white/75">
                Izin kamera ditolak atau perangkat tidak punya kamera. Unggah foto
                dari galeri saja.
              </p>
            </div>
          ) : (
            <div className="relative h-44 w-64">
              <span className="absolute left-0 top-0 h-7 w-7 rounded-tl-lg border-l-[3px] border-t-[3px] border-white" />
              <span className="absolute right-0 top-0 h-7 w-7 rounded-tr-lg border-r-[3px] border-t-[3px] border-white" />
              <span className="absolute bottom-0 left-0 h-7 w-7 rounded-bl-lg border-b-[3px] border-l-[3px] border-white" />
              <span className="absolute bottom-0 right-0 h-7 w-7 rounded-br-lg border-b-[3px] border-r-[3px] border-white" />
              <div className="absolute left-1/2 top-1/2 flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-gold shadow-[0_0_18px_rgba(242,185,77,0.6)]">
                <span className="h-2 w-2 rounded-full bg-gold shadow-[0_0_9px_#F2B94D]" />
              </div>
            </div>
          )}
        </div>

        {/* kontrol bawah: galeri · shutter · flip */}
        <div className="flex items-center justify-between px-8 pb-10">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            title="Unggah dari galeri"
            className="glass flex h-14 w-14 items-center justify-center rounded-2xl text-white transition active:scale-90"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="3" />
              <circle cx="8.5" cy="9" r="1.6" />
              <path d="M4 18l5-5 4 4 3-3 4 4" />
            </svg>
          </button>

          <button
            type="button"
            onClick={shoot}
            disabled={denied}
            title="Ambil foto"
            className="flex h-20 w-20 items-center justify-center rounded-full border-[5px] border-white/50 bg-white/25 shadow-[0_8px_22px_rgba(0,0,0,0.4)] backdrop-blur transition active:scale-95 disabled:opacity-40"
          >
            <span className="h-14 w-14 rounded-full bg-gradient-to-b from-accent-blue to-accent-blue-link shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]" />
          </button>

          <button
            type="button"
            onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
            title="Balik kamera"
            className="glass flex h-14 w-14 items-center justify-center rounded-2xl text-white transition active:scale-90"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 12a8 8 0 0 1 13-6l3 2M20 12a8 8 0 0 1-13 6l-3-2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
