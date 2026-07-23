/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // Token dari docs/notes/design_tokens.md (prototipe Claude Design).
  theme: {
    extend: {
      colors: {
        navy: {
          base: "#0b1f4d", // base body
          from: "#1f3a7a", // gradient layar biasa
          to: "#122a5e",
          "loading-from": "#16337a", // gradient layar loading
          "loading-to": "#0c1f52",
        },
        gold: "#F2B94D",
        "accent-blue": { DEFAULT: "#4f8bff", link: "#2F6FEB" },
        "accent-green": "#2f9e6e",
        "accent-purple": "#7a5cff",
        "accent-red": "#D2483F",
      },
      fontFamily: {
        sans: ["'Plus Jakarta Sans'", "sans-serif"], // body
        display: ["Lexend", "sans-serif"], // judul/branding
        mono: ["'JetBrains Mono'", "monospace"], // kode aditif, skor, referensi
      },
      // "Scan": garis bergerak naik-turun untuk state loading (docs/notes/design_tokens.md).
      keyframes: {
        scan: {
          "0%, 100%": { top: "0%" },
          "50%": { top: "100%" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-160px 0" },
          "100%": { backgroundPosition: "220px 0" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        // Aperture loading (ROW 1.8): titik lensa berdenyut & langkah berkedip.
        "pulse-ring": {
          "0%, 100%": { transform: "translate(-50%,-50%) scale(1)", opacity: "0.9" },
          "50%": { transform: "translate(-50%,-50%) scale(1.18)", opacity: "0.4" },
        },
        "fade-blink": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        scan: "scan 2s ease-in-out infinite",
        float: "float 3.4s ease-in-out infinite",
        shimmer: "shimmer 1.1s linear infinite",
        // fill-mode 'backwards' (bukan 'both'): cegah kedip di awal TANPA
        // menyisakan transform setelah selesai. Transform yang tersisa akan jadi
        // containing block dan merusak posisi 'fixed' overlay kamera/modal.
        "fade-up": "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) backwards",
        "pulse-ring": "pulse-ring 1.6s ease-in-out infinite",
        "fade-blink": "fade-blink 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
