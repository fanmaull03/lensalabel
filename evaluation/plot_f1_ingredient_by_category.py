"""Render F1 identification of canonical ingredients by KB category."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation/results/chapter4/tabel_metrik_160.csv"
OUTPUT = ROOT / "evaluation/results/chapter4/gambar_4_x_f1_identifikasi_bahan_per_kategori.png"


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    categories = [("aman", "Aman"), ("perhatian", "Perlu Perhatian"), ("hindari", "Hindari")]
    values, lower, upper = [], [], []
    for key, _ in categories:
        matches = [row for row in rows if row["level"] == "ingredient"
                   and row["cakupan"] == "keseluruhan"
                   and row["kategori"] == key and row["metrik"] == "f1"
                   and row["jumlah_foto"] == "160"]
        if len(matches) != 1:
            raise ValueError(f"Expected one final ingredient F1 row for {key}")
        row = matches[0]
        values.append(float(row["nilai"]))
        lower.append(float(row["ci95_bawah"]))
        upper.append(float(row["ci95_atas"]))

    fig, ax = plt.subplots(figsize=(9.2, 5.5))
    x = np.arange(len(categories))
    colors = ["#4c8f7c", "#cf9850", "#b65b54"]
    error = [np.array(values) - np.array(lower), np.array(upper) - np.array(values)]
    bars = ax.bar(x, values, width=.56, color=colors, yerr=error, capsize=6,
                  error_kw={"elinewidth": 1.6, "capthick": 1.6})
    for bar, value, high in zip(bars, values, upper):
        ax.text(bar.get_x() + bar.get_width()/2, high + .028,
                f"{value:.3f}".replace(".", ","), ha="center", va="bottom",
                fontsize=12, weight="bold", color="#20343d")

    ax.set_xticks(x, [name for _, name in categories])
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("F1-score identifikasi bahan")
    ax.set_title("Perbandingan F1-score identifikasi bahan berdasarkan kategori",
                 loc="left", weight="bold", pad=20)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    fig.text(.13, .037,
             "Evaluasi akhir: 160 foto. Garis menunjukkan CI 95% dari 1.000 bootstrap per foto.",
             fontsize=8.6, color="#526169")
    fig.text(.13, .017, "Yang dinilai adalah identitas bahan, bukan hanya kategori.",
             fontsize=8.6, color="#526169")
    fig.tight_layout(rect=(0, .09, 1, 1))
    fig.savefig(OUTPUT, dpi=300, facecolor="white")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
