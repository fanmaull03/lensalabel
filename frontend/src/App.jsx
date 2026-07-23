// Root component - routing antar pages
import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import ResultPage from "./pages/ResultPage";
import GfcfEducationPage from "./pages/GfcfEducationPage";
import AboutPage from "./pages/AboutPage";

// Membungkus Routes dengan key = pathname supaya React remount tiap pindah
// halaman; animasi masuk (fade-up) diputar ulang. Harus di dalam Router agar
// useLocation() bisa dipakai.
function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-fade-up">
      <Routes location={location}>
        <Route path="/" element={<UploadPage />} />
        <Route path="/hasil" element={<ResultPage />} />
        <Route path="/edukasi" element={<GfcfEducationPage />} />
        <Route path="/tentang" element={<AboutPage />} />
      </Routes>
    </div>
  );
}

// Dock bawah (mockup): item nyata yang ada halamannya. Cari/Riwayat sengaja
// tidak dipasang — di luar cakupan (tidak ada backend/penyimpanannya).
const CameraIcon = (
  <>
    <rect x="3" y="7" width="18" height="13" rx="3" />
    <circle cx="12" cy="13.5" r="3.4" />
    <path d="M8.5 7l1.2-2h4.6L15.5 7" />
  </>
);
const BookIcon = (
  <>
    <path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" />
    <line x1="9" y1="8" x2="14" y2="8" />
  </>
);
const InfoIcon = (
  <>
    <circle cx="12" cy="12" r="9" />
    <line x1="12" y1="11" x2="12" y2="16" />
    <circle cx="12" cy="7.8" r="0.6" fill="currentColor" />
  </>
);

const NAV = [
  { to: "/", label: "Pindai", icon: CameraIcon },
  { to: "/edukasi", label: "Edukasi", icon: BookIcon },
  { to: "/tentang", label: "Tentang", icon: InfoIcon },
];

function BottomBar() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-10 border-t border-white/20 bg-white/10 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]">
      <div className="mx-auto flex max-w-md justify-around px-2 py-2">
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 rounded-xl py-1.5 text-xs font-medium transition duration-200 active:scale-90 ${
                isActive ? "text-white" : "text-white/55 hover:text-white/80"
              }`
            }
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {icon}
            </svg>
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen text-white">
        {/* pb besar supaya konten terakhir tidak tertutup dock */}
        <main className="mx-auto max-w-md px-4 pb-28 pt-6">
          <AnimatedRoutes />
        </main>
        <BottomBar />
      </div>
    </BrowserRouter>
  );
}
