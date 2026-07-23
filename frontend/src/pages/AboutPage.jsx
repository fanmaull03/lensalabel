// Halaman "Tentang / Info Sistem" (mockup 07). Statis: accordion penjelasan
// aplikasi, cara kerja, definisi kategori, sumber data, batasan, & pengembang.
// Tidak menyentuh backend — murni informatif.
import { useState } from "react";
import logo from "../assets/lensalabel_logo.png";

// Definisi kategori memakai warna fungsional yang sama dengan verdict
// (hijau=Aman, kuning=Perhatian, merah=Hindari) — jangan diubah.
const CATEGORIES = [
  {
    label: "Aman",
    color: "border-emerald-400 text-emerald-700",
    body: "Bahan yang aman dikonsumsi anak autisme dalam konteks diet GFCF.",
  },
  {
    label: "Perhatian",
    color: "border-amber-400 text-amber-700",
    body: "Bahan yang boleh dikonsumsi namun perlu dibatasi jumlahnya.",
  },
  {
    label: "Hindari",
    color: "border-red-400 text-red-700",
    body: "Bahan yang sebaiknya tidak dikonsumsi anak autisme.",
  },
];

const STEPS = [
  "Foto atau unggah label komposisi kemasan makanan.",
  "LensaLabel membaca teks pada label menggunakan pengenalan karakter (OCR).",
  "Setiap bahan dicocokkan dengan basis data yang disusun dari literatur ilmiah.",
  "Anda melihat status keamanan tiap bahan: Aman, Perhatian, atau Hindari.",
];

// Konten tiap seksi; sebagian dirender khusus (steps/kategori) lewat `render`.
const SECTIONS = [
  {
    title: "Apa itu LensaLabel",
    body: "LensaLabel membantu Anda memeriksa keamanan bahan makanan pada label kemasan untuk anak dengan kebutuhan diet Gluten-Free Casein-Free (GFCF). Cukup foto label komposisi, dan LensaLabel membantu mengenali bahan yang perlu diperhatikan — tanpa harus menghafal istilah teknis di baliknya.",
  },
  { title: "Cara Kerja Sistem", render: "steps" },
  { title: "Definisi Kategori", render: "categories" },
  {
    title: "Sumber & Validasi Basis Data",
    body: "Basis data bahan makanan disusun berdasarkan kajian literatur ilmiah terkait diet GFCF dan pengaruh bahan tambahan pangan terhadap kondisi anak dengan Autism Spectrum Disorder (ASD), yang telah ditinjau oleh tenaga ahli di bidang medis/gizi anak.",
  },
  {
    title: "Batasan & Hal Penting",
    body: "LensaLabel adalah alat bantu informasi, bukan pengganti diagnosis atau saran dari dokter maupun ahli gizi. Klasifikasi keamanan ditujukan khusus untuk konteks diet GFCF pada anak ASD, bukan panduan diet kesehatan umum. Sistem hanya membaca teks tercetak yang jelas; hasil pada kemasan rusak, buram, atau tulisan tangan bisa kurang akurat — selalu periksa ulang bila ragu. Aplikasi ini dikembangkan sebagai bagian dari tugas akhir (skripsi) dan masih dalam tahap penelitian.",
  },
  {
    title: "Tentang Pengembang",
    body: "LensaLabel dikembangkan oleh Muhammad Ifan Sidiq Maulana, mahasiswa Informatika, Fakultas Teknik, Universitas Jenderal Soedirman, sebagai bagian dari tugas akhir (skripsi). Informatika · Fakultas Teknik · UNSOED · 2026",
  },
];

export default function AboutPage() {
  // Seksi pertama & "Batasan" terbuka secara default (paling sering dibaca).
  const [open, setOpen] = useState({ 0: true, 4: true });
  const toggle = (i) => setOpen((s) => ({ ...s, [i]: !s[i] }));

  return (
    <div className="space-y-4 font-sans">
      <div className="text-center">
        <img
          src={logo}
          alt="LensaLabel"
          className="mx-auto h-[74px] w-[74px] object-contain drop-shadow-[0_4px_8px_rgba(0,0,0,0.3)]"
        />
        <h1 className="mt-2 font-display text-2xl font-extrabold text-white">
          Lensa<span className="text-accent-blue">Label</span>
        </h1>
        <p className="mt-1 text-sm font-medium text-gold">
          Lihat Jelas Komposisi, Pilih dengan Pasti.
        </p>
        <p className="mt-3 text-xs text-white/55">Ketuk tiap bagian untuk membuka.</p>
      </div>

      <div className="space-y-3">
        {SECTIONS.map((section, i) => (
          <div key={section.title} className="glass-white overflow-hidden rounded-2xl shadow-xl">
            <button
              type="button"
              onClick={() => toggle(i)}
              aria-expanded={!!open[i]}
              className="flex w-full items-center justify-between px-4 py-4 text-left transition duration-200 hover:bg-white/40"
            >
              <span className="font-display text-sm font-bold text-navy-base">
                {section.title}
              </span>
              <span
                className={`text-accent-blue-link transition-transform duration-300 ${open[i] ? "rotate-180" : ""}`}
              >
                ▾
              </span>
            </button>
            {/* Animasi buka/tutup via grid-rows 0fr->1fr: tinggi ter-animasi
                mulus dua arah tanpa mengukur tinggi konten dengan JS. */}
            <div
              className={`grid transition-all duration-300 ease-out ${
                open[i] ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
              }`}
            >
              <div className="overflow-hidden">
                <div className="px-4 pb-4 text-sm leading-relaxed text-slate-600">
                  {section.render === "steps" ? (
                  <ol className="space-y-3">
                    {STEPS.map((step, n) => (
                      <li key={n} className="flex gap-3">
                        <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent-blue-link text-xs font-bold text-white">
                          {n + 1}
                        </span>
                        <span className="pt-0.5">{step}</span>
                      </li>
                    ))}
                  </ol>
                ) : section.render === "categories" ? (
                  <div className="space-y-2">
                    {CATEGORIES.map((c) => (
                      <div key={c.label} className={`rounded-xl border-l-4 bg-slate-50 px-3 py-2 ${c.color}`}>
                        <div className="text-sm font-bold">{c.label}</div>
                        <div className="mt-0.5 text-xs text-slate-600">{c.body}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  section.body
                )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
