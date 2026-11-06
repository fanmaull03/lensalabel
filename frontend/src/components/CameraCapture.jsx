// Layar kamera live full-bleed (desain KAMERA FULL-BLEED). Pakai MediaDevices
// bawaan browser — tanpa library. Shutter menangkap satu frame video ke canvas
// lalu mengirimnya sebagai File JPEG, bentuk yang sama seperti input file, jadi
// pipeline /identify tidak berubah.
import { useEffect, useRef, useState } from "react";
import logo from "../assets/lensalabel_logo.png";
import { cameraCrop } from "../utils/cameraCrop";

export default function CameraCapture({ onCapture, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const guideRef = useRef(null);
  const [facing, setFacing] = useState("environment");
  const [denied, setDenied] = useState(false);
  const [preview, setPreview] = useState(null);
  const [captureError, setCaptureError] = useState("");

  // Revoke blob URL preview sebelumnya setiap kali URL berubah, dan pastikan
  // URL terakhir ikut dilepas saat unmount (ref diisi URL aktif). Dependensi
  // harus preview?.url, bukan objek preview — objek yang sama bisa menampung
  // URL yang sudah mati setelah cleanup berjalan.
  const previewUrlRef = useRef(null);
  useEffect(() => {
    previewUrlRef.current = preview?.url ?? null;
    return () => {
      if (preview?.url) URL.revokeObjectURL(preview.url);
    };
  }, [preview?.url]);
  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  useEffect(() => {
    let active = true;
    async function start() {
      setDenied(false);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facing },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
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
    const guide = guideRef.current;
    if (!video?.videoWidth || !video.videoHeight || !guide) {
      setCaptureError("Kamera belum siap. Coba beberapa saat lagi.");
      return;
    }
    const crop = cameraCrop(
      { width: video.videoWidth, height: video.videoHeight },
      video.getBoundingClientRect(), guide.getBoundingClientRect(),
    );
    if (crop.width < 400 || crop.height < 300) {
      setCaptureError("Resolusi kamera terlalu rendah untuk membaca komposisi. Gunakan foto dari galeri.");
      return;
    }
    setCaptureError("");
    const canvas = document.createElement("canvas");
    canvas.width = crop.width;
    canvas.height = crop.height;
    try {
      canvas.getContext("2d").drawImage(
        video, crop.x, crop.y, crop.width, crop.height, 0, 0, crop.width, crop.height,
      );
    } catch {
      // Koordinat crop di luar frame video (layout viewport ekstrem): jangan
      // biarkan exception mentah mematikan shutter tanpa pesan.
      setCaptureError("Gagal memotong area foto. Coba ambil ulang.");
      return;
    }
    canvas.toBlob(
      (blob) => blob
        ? setPreview({
          file: new File([blob], "kamera.jpg", { type: "image/jpeg" }),
          url: URL.createObjectURL(blob),
          width: crop.width,
          height: crop.height,
        })
        : setCaptureError("Foto gagal dibuat. Coba ambil ulang."),
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
            {preview ? "Periksa apakah semua tulisan terbaca jelas" : <>
              Posisikan <b>seluruh daftar komposisi</b> di dalam bingkai
            </>}
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
        <div className="flex min-h-0 flex-1 items-center justify-center p-6">
          {denied ? (
            <div className="max-w-xs rounded-2xl border border-white/25 bg-navy-base/50 p-6 text-center text-white backdrop-blur-xl">
              <p className="font-display text-lg font-bold">Kamera tidak bisa diakses</p>
              <p className="mt-2 text-sm text-white/75">
                Izin kamera ditolak atau perangkat tidak punya kamera. Unggah foto
                dari galeri saja.
              </p>
            </div>
          ) : (
            <div ref={guideRef} className="relative h-full w-full max-w-lg">
              {preview && <img src={preview.url} alt="Pratinjau foto komposisi" className="h-full w-full object-contain" />}
              <span className="absolute left-0 top-0 h-7 w-7 rounded-tl-lg border-l-[3px] border-t-[3px] border-white" />
              <span className="absolute right-0 top-0 h-7 w-7 rounded-tr-lg border-r-[3px] border-t-[3px] border-white" />
              <span className="absolute bottom-0 left-0 h-7 w-7 rounded-bl-lg border-b-[3px] border-l-[3px] border-white" />
              <span className="absolute bottom-0 right-0 h-7 w-7 rounded-br-lg border-b-[3px] border-r-[3px] border-white" />
              {!preview && <div className="absolute left-1/2 top-1/2 flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-gold shadow-[0_0_18px_rgba(242,185,77,0.6)]">
                <span className="h-2 w-2 rounded-full bg-gold shadow-[0_0_9px_#F2B94D]" />
              </div>}
            </div>
          )}
        </div>

        {captureError && <p role="alert" className="px-6 pb-3 text-center text-sm text-white">{captureError}</p>}
        {preview && <p className="px-6 pb-3 text-center text-xs text-white/75">Foto {preview.width} × {preview.height} piksel</p>}
        {/* kontrol bawah: galeri · shutter · flip */}
        {preview ? (
          <div className="flex gap-3 px-6 pb-10">
            <button type="button" onClick={() => setPreview(null)} className="glass flex-1 rounded-2xl px-4 py-4 font-semibold text-white">Ambil Ulang</button>
            <button type="button" onClick={() => onCapture(preview.file)} className="flex-1 rounded-2xl bg-accent-blue px-4 py-4 font-semibold text-white">Gunakan Foto</button>
          </div>
        ) : <div className="flex items-center justify-between px-8 pb-10">
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
        </div>}
      </div>
    </div>
  );
}
