// Daftar bahan per kategori. Grup kosong tidak dirender sama sekali.
// onSelect(item) dipanggil saat satu bahan ditap -> ResultPage buka Detail.
import IngredientBadge from "./IngredientBadge";

const GROUPS = [
  { key: "hindari", title: "Hindari" },
  { key: "perhatian", title: "Perlu Perhatian" },
  { key: "aman", title: "Aman" },
  { key: "tidak_dikenali", title: "Tidak Dikenali Sistem" },
];

export default function ResultList({ result, onSelect }) {
  return (
    <div className="space-y-5">
      {GROUPS.map(({ key, title }) => {
        const items = result[key] ?? [];
        if (items.length === 0) return null;
        return (
          <section key={key}>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/60">
              {title} ({items.length})
            </h2>
            <ul className="space-y-2">
              {items.map((item, i) => {
                // Normalkan dua bentuk item (cocok vs tidak_dikenali) jadi satu
                // objek yang dipakai badge maupun Detail.
                const detail =
                  key === "tidak_dikenali"
                    ? { name: item.token, category: key, matched: null, score: item.score, terdekat: item.terdekat }
                    : { name: item.standard_name, category: key, matched: item.matched_window, score: item.score, terdekat: null };
                return (
                  <IngredientBadge
                    key={i}
                    name={detail.name}
                    category={key}
                    detail={
                      key === "tidak_dikenali"
                        ? "tidak ditemukan di basis data"
                        : `terbaca: "${item.matched_window}"`
                    }
                    onClick={() => onSelect(detail)}
                  />
                );
              })}
            </ul>
            {key === "tidak_dikenali" && (
              <p className="mt-2 text-xs text-white/55">
                Bagian komposisi di atas tidak dikenali sistem. Periksa sendiri
                bagian ini pada label asli, jangan anggap otomatis aman.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
