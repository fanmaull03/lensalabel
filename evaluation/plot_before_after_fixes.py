"""Bandingkan hasil evaluasi 160 foto SEBELUM vs SESUDAH perbaikan bug
(tokenizer titik, stopword boilerplate, strip marker pembuka) dan hasilkan
gambar PNG siap-laporan di evaluation/results/before_after_fixes/.

Data lama dibaca dari backup results/evaluation_ocr_before_fixes/ (disalin
sebelum evaluasi ulang); data baru dari results/evaluation_ocr/ hasil
evaluate_160_metrics.py terbaru. Kedua run memakai cache OCR yang SAMA
(evaluation_ocr_160.csv), jadi metrik CER/WER identik dan seluruh perbedaan
berasal dari perubahan kode matcher/tokenizer.

Jalankan dari root proyek:
    backend\\.venv\\Scripts\\python.exe evaluation\\plot_before_after_fixes.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OLD_DIR = ROOT / "evaluation" / "results" / "evaluation_ocr_before_fixes"
NEW_DIR = ROOT / "evaluation" / "results" / "evaluation_ocr"
OUT_DIR = ROOT / "evaluation" / "results" / "before_after_fixes"

CATEGORIES = ("aman", "perhatian", "hindari")
CAT_LABEL = {"aman": "Aman", "perhatian": "Perhatian", "hindari": "Hindari"}
METRICS = ("precision", "recall", "f1")
METRIC_LABEL = {"precision": "Presisi", "recall": "Recall", "f1": "F1"}

C_OLD = "#94a3b8"   # slate-400
C_NEW = "#2563eb"   # blue-600
C_POS = "#16a34a"   # green-600
C_NEG = "#dc2626"   # red-600


def load_summary(path: Path) -> dict[tuple, dict]:
    with open(path, encoding="utf-8-sig") as f:
        return {
            (r["level"], r["cakupan"], r["kategori"], r["metrik"]): {
                "nilai": float(r["nilai"]),
                "lo": float(r["ci95_bawah"]),
                "hi": float(r["ci95_atas"]),
            }
            for r in csv.DictReader(f)
        }


def load_confusion(path: Path) -> np.ndarray:
    m = np.zeros((3, 3), dtype=int)
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["cakupan"] == "keseluruhan":
                i = CATEGORIES.index(r["verdict_gt"])
                j = CATEGORIES.index(r["verdict_prediksi"])
                m[i, j] = int(r["jumlah"])
    return m


def load_status_counts(path: Path) -> dict[str, int]:
    with open(path, encoding="utf-8-sig") as f:
        return {r["status_sistem"]: int(r["jumlah"]) for r in csv.DictReader(f)}


def load_detail(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig") as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def style_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- figure 1
def fig_grouped_metrics(old, new):
    """Bar berkelompok: level ingredient & kategori, keseluruhan, P/R/F1."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, level, title in (
        (axes[0], "ingredient", "Identifikasi Bahan (nama standar)"),
        (axes[1], "category", "Klasifikasi Kategori Keamanan"),
    ):
        x = np.arange(len(METRICS))
        w = 0.36
        vals_old, vals_new, err_lo, err_hi = [], [], [], []
        for m in METRICS:
            o = old[(level, "keseluruhan", "semua", m)]
            n = new[(level, "keseluruhan", "semua", m)]
            vals_old.append(o["nilai"] * 100)
            vals_new.append(n["nilai"] * 100)
            err_lo.append((n["nilai"] - n["lo"]) * 100)
            err_hi.append((n["hi"] - n["nilai"]) * 100)
        b1 = ax.bar(x - w / 2, vals_old, w, label="Sebelum perbaikan", color=C_OLD)
        b2 = ax.bar(
            x + w / 2, vals_new, w, label="Sesudah perbaikan", color=C_NEW,
            yerr=[err_lo, err_hi], capsize=4, error_kw={"linewidth": 1},
        )
        for b in b1:
            ax.annotate(
                f"{b.get_height():.1f}",
                (b.get_x() + b.get_width() / 2, b.get_height()),
                ha="center", va="bottom", fontsize=8.5,
            )
        # Label nilai diletakkan di ATAS tutup error bar, bukan di atas batang,
        # supaya whisker CI tidak menembus angka.
        for b, hi in zip(b2, err_hi):
            ax.annotate(
                f"{b.get_height():.1f}",
                (b.get_x() + b.get_width() / 2, b.get_height() + hi + 0.6),
                ha="center", va="bottom", fontsize=8.5,
            )
        ax.set_xticks(x, [METRIC_LABEL[m] for m in METRICS])
        ax.set_ylim(0, 112)
        ax.set_ylabel("Skor (%)")
        ax.set_title(title, fontsize=11, fontweight="bold")
        style_ax(ax)
    axes[1].legend(loc="lower right", fontsize=9)
    fig.suptitle(
        "Metrik Evaluasi 160 Foto: Sebelum vs Sesudah Perbaikan\n"
        "(bilah error = CI 95% bootstrap 1000 resampling pada hasil sesudah)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


# ---------------------------------------------------------------- figure 2
def fig_confusion_pair(old_cm, new_cm):
    """Confusion matrix verdict produk (3 kelas), lama vs baru berdampingan."""
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6))
    labels = [CAT_LABEL[c] for c in CATEGORIES]
    for ax, cm, title, acc in (
        (axes[0], old_cm, "Sebelum perbaikan", np.trace(old_cm)),
        (axes[1], new_cm, "Sesudah perbaikan", np.trace(new_cm)),
    ):
        im = ax.imshow(cm, cmap="Blues", vmin=0, vmax=cm.max())
        for i in range(3):
            for j in range(3):
                color = "white" if cm[i, j] > cm.max() * 0.55 else "black"
                weight = "bold" if i == j else "normal"
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        fontsize=13, color=color, fontweight=weight)
        ax.set_xticks(range(3), labels)
        ax.set_yticks(range(3), labels)
        ax.set_xlabel("Verdict Prediksi")
        ax.set_ylabel("Verdict Ground Truth")
        ax.set_title(f"{title}\nakurasi {acc}/160 = {acc / 160:.1%}", fontsize=11,
                     fontweight="bold")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle(
        "Confusion Matrix Verdict Produk (3 kelas)\n"
        "Status perlu_verifikasi/tidak_terbaca dipetakan ke Perhatian",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    return fig


# ---------------------------------------------------------------- figure 3
def fig_status_and_flips(old_status, new_status, flips):
    """Kiri: jumlah status sistem 5 nilai. Kanan: 3 foto yang berubah verdict."""
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1, 1.15]}
    )
    order = ["aman", "perhatian", "hindari", "perlu_verifikasi", "tidak_terbaca"]
    label = {
        "aman": "Aman", "perhatian": "Perhatian", "hindari": "Hindari",
        "perlu_verifikasi": "Perlu Verifikasi", "tidak_terbaca": "Tidak Terbaca",
    }
    x = np.arange(len(order))
    w = 0.36
    v_old = [old_status.get(k, 0) for k in order]
    v_new = [new_status.get(k, 0) for k in order]
    b1 = ax1.bar(x - w / 2, v_old, w, label="Sebelum", color=C_OLD)
    b2 = ax1.bar(x + w / 2, v_new, w, label="Sesudah", color=C_NEW)
    for bars in (b1, b2):
        for b in bars:
            if b.get_height():
                ax1.annotate(f"{int(b.get_height())}",
                             (b.get_x() + b.get_width() / 2, b.get_height()),
                             ha="center", va="bottom", fontsize=9)
    ax1.set_xticks(x, [label[k] for k in order], rotation=18, ha="right")
    ax1.set_ylabel("Jumlah foto")
    ax1.set_ylim(0, 108)
    ax1.legend(fontsize=9)
    ax1.set_title("Distribusi Status Sistem (5 nilai)", fontsize=11,
                  fontweight="bold")
    style_ax(ax1)

    ax2.axis("off")
    ax2.set_title("Foto yang Berubah Verdict (3 dari 160)", fontsize=11,
                  fontweight="bold", loc="left")
    header = ["Foto", "GT", "Sebelum", "Sesudah", "Efek"]
    # Kolom Foto harus muat "melengkung_067.jpeg" (19 karakter) — kalau terlalu
    # sempit, nama file menimpa kolom GT.
    widths = [0.32, 0.15, 0.15, 0.15, 0.23]
    y = 0.88
    for i, h in enumerate(header):
        ax2.text(sum(widths[:i]), y, h, fontsize=9.5,
                 fontweight="bold", transform=ax2.transAxes)
    y -= 0.045
    ax2.plot([0, 1], [y, y], color="black", lw=0.8, transform=ax2.transAxes)
    for row in flips:
        y -= 0.095
        fn, gt, was, now, good = row
        vals = [fn, CAT_LABEL[gt], CAT_LABEL[was], CAT_LABEL[now],
                "✔ menjadi benar" if good else "✘ menjadi salah"]
        color = C_POS if good else C_NEG
        for i, v in enumerate(vals):
            ax2.text(sum(widths[:i]), y, v, fontsize=9,
                     color=color if i == 4 else "black",
                     fontweight="bold" if i == 4 else "normal",
                     transform=ax2.transAxes)
    # Catatan diletakkan jauh di bawah baris tabel terakhir dengan jarak yang
    # pasti, bukan offset relatif yang bisa bertumpuk dengan baris.
    ax2.text(
        0, 0.30,
        "Keterangan: ketiga perubahan berasal dari strip marker pembuka\n"
        "yang lebih ketat — bahan yang sebelumnya ikut terpotong kini tetap\n"
        "terbaca, sehingga token tak dikenal muncul dan status sistem menjadi\n"
        "perlu_verifikasi (terpetakan ke Perhatian pada matriks 3 kelas).",
        fontsize=8.5, transform=ax2.transAxes, color="#444444", va="top",
    )
    fig.suptitle("Dampak Perbaikan pada Status & Verdict Produk",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    return fig


# ---------------------------------------------------------------- figure 4
def fig_category_recall_delta(old, new):
    """Delta recall per kategori per kondisi — perbaikan terbesar ada di recall."""
    groups = [("keseluruhan", "Keseluruhan"), ("datar", "Datar"),
              ("melengkung", "Melengkung")]
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    x = np.arange(len(groups))
    w = 0.26
    for k, cat in enumerate(CATEGORIES):
        deltas = []
        for cov, _ in groups:
            o = old[("category", cov, cat, "recall")]["nilai"]
            n = new[("category", cov, cat, "recall")]["nilai"]
            deltas.append((n - o) * 100)
        bars = ax.bar(x + (k - 1) * w, deltas, w, label=CAT_LABEL[cat],
                      color=["#16a34a", "#d97706", "#dc2626"][k], alpha=0.85)
        for b, d in zip(bars, deltas):
            ax.annotate(f"{d:+.1f}", (b.get_x() + b.get_width() / 2,
                                      b.get_height() + (0.4 if d >= 0 else -1.8)),
                        ha="center", fontsize=8.5)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x, [g[1] for g in groups])
    ax.set_ylabel("Perubahan recall (poin persen)")
    ax.set_title("Perubahan Recall Klasifikasi Kategori per Kondisi Kemasan\n"
                 "(sesudah − sebelum perbaikan)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    style_ax(ax)
    fig.tight_layout()
    return fig


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    old = load_summary(OLD_DIR / "evaluation_metrics_summary.csv")
    new = load_summary(NEW_DIR / "evaluation_metrics_summary.csv")
    old_cm = load_confusion(OLD_DIR / "evaluation_verdict_confusion.csv")
    new_cm = load_confusion(NEW_DIR / "evaluation_verdict_confusion.csv")
    old_status = load_status_counts(OLD_DIR / "evaluation_system_status_counts.csv")
    new_status = load_status_counts(NEW_DIR / "evaluation_system_status_counts.csv")
    old_d = load_detail(OLD_DIR / "evaluation_metrics_detail.csv")
    new_d = load_detail(NEW_DIR / "evaluation_metrics_detail.csv")

    flips = []
    for fn in sorted(old_d):
        o, n = old_d[fn], new_d[fn]
        if o["pred_verdict"] != n["pred_verdict"]:
            good = n["pred_verdict"] == n["gt_verdict"]
            flips.append((fn, n["gt_verdict"], o["pred_verdict"],
                          n["pred_verdict"], good))

    figures = {
        "gambar_perbandingan_metrik.png": fig_grouped_metrics(old, new),
        "gambar_confusion_matrix_verdict.png": fig_confusion_pair(old_cm, new_cm),
        "gambar_status_dan_perubahan.png": fig_status_and_flips(old_status, new_status, flips),
        "gambar_delta_recall_kategori.png": fig_category_recall_delta(old, new),
    }
    for name, fig in figures.items():
        fig.savefig(OUT_DIR / name, dpi=200, bbox_inches="tight",
                    facecolor="white")
        plt.close(fig)
        print("tersimpan:", OUT_DIR / name)

    # Ringkasan angka untuk narasi laporan (mesin-baca + manusia-baca).
    def row(summary, level, cat, metric):
        v = summary[(level, "keseluruhan", cat, metric)]
        return {"nilai": v["nilai"], "ci95_bawah": v["lo"], "ci95_atas": v["hi"]}

    comparison = {
        "catatan": "Kedua run memakai cache OCR yang sama; CER/WER identik. "
                   "Perbedaan murni dari perbaikan tokenizer/matcher/routes.",
        "ingredient_keseluruhan": {m: {"sebelum": row(old, "ingredient", "semua", m),
                                       "sesudah": row(new, "ingredient", "semua", m)}
                                   for m in METRICS},
        "kategori_keseluruhan": {m: {"sebelum": row(old, "category", "semua", m),
                                     "sesudah": row(new, "category", "semua", m)}
                                 for m in METRICS},
        "akurasi_verdict": {"sebelum": int(np.trace(old_cm)),
                            "sesudah": int(np.trace(new_cm)), "total": 160},
        "foto_berubah_verdict": [
            {"foto": f[0], "gt": f[1], "sebelum": f[2], "sesudah": f[3],
             "menjadi_benar": f[4]}
            for f in flips
        ],
    }
    with open(OUT_DIR / "ringkasan_perbandingan.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    print("tersimpan:", OUT_DIR / "ringkasan_perbandingan.json")


if __name__ == "__main__":
    main()
