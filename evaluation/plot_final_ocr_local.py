"""Plot final CER/WER for the locally aligned composition text region."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation/results/evaluation_ocr/evaluation_metrics_summary.csv"
OUTPUT = ROOT / "evaluation/results/chapter4/gambar_4_02_cer_wer_kondisi.png"


def main(output: Path = OUTPUT) -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    data = {}
    for condition in ("Datar", "Melengkung"):
        for metric in ("CER", "WER"):
            matches = [row for row in rows if row["level"] == metric
                       and row["cakupan"] == condition
                       and row["kategori"] == "lokal"
                       and row["metrik"] == "mean"
                       and row["jumlah_foto"] == "80"]
            if len(matches) != 1:
                raise ValueError(f"Expected one final local OCR metric: {condition} {metric}")
            row = matches[0]
            data[condition, metric] = tuple(float(row[key]) for key in
                                            ("nilai", "ci95_bawah", "ci95_atas"))

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    x = np.arange(2)
    width = 0.32
    colors = {"CER": "#31778b", "WER": "#d5924e"}
    for metric, shift in (("CER", -width / 2), ("WER", width / 2)):
        values = [data[condition, metric][0] for condition in ("Datar", "Melengkung")]
        low = [value - data[condition, metric][1] for condition, value in zip(("Datar", "Melengkung"), values)]
        high = [data[condition, metric][2] - value for condition, value in zip(("Datar", "Melengkung"), values)]
        bars = ax.bar(x + shift, values, width, color=colors[metric], label=metric,
                      yerr=[low, high], capsize=5, error_kw={"elinewidth": 1.5})
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, value + .055, f"{value:.3f}",
                    ha="center", va="bottom", fontsize=10)
    ax.set_xticks(x, ["Datar (n=80)", "Melengkung (n=80)"])
    ax.set_ylim(0, .68)
    ax.set_ylabel("Rata-rata tingkat galat")
    ax.set_title("CER dan WER lokal menurut kondisi kemasan", loc="left", weight="bold", pad=18)
    ax.legend(frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    fig.text(.13, .015, "Wilayah komposisi yang disejajarkan dengan transkrip; galat di luar wilayah ini tidak dihitung."
             "  Garis: CI 95% bootstrap per foto.", fontsize=8.4, color="#4d5d64")
    fig.tight_layout(rect=(0, .055, 1, 1))
    fig.savefig(output, dpi=300, facecolor="white")
    plt.close(fig)
    print(output)
    for key, value in data.items():
        print(key, value)


if __name__ == "__main__":
    main()
