"""Package aggregate 160-photo evaluation tables with final Chapter IV assets.

This script reads persisted summaries only. It does not load per-photo
predictions, rerun OCR, call the matcher, or recompute any metric.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation/results/evaluation_ocr"
OUTPUT = ROOT / "evaluation/results/chapter4"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0]) if rows else ["status"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def style(ws) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="264653")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column in ws.columns:
        letter = column[0].column_letter
        ws.column_dimensions[letter].width = min(38, max(12, max(len(str(c.value or "")) for c in column) + 2))
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def write_workbook(path: Path, sheets: dict[str, list[dict[str, str]]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        ws = workbook.create_sheet(name[:31])
        fields = list(rows[0]) if rows else ["status"]
        ws.append(fields)
        for row in rows:
            ws.append([row.get(field, "") for field in fields])
        style(ws)
    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None,
                        help="Nama berkas konfigurasi beku, mis. config_frozen_v2.json. Default: config_frozen.json.")
    args = parser.parse_args()
    config_path = ROOT / "evaluation" / (args.config or "config_frozen.json")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if config.get("status") != "frozen":
        raise RuntimeError("Paket final hanya boleh dibuat dari konfigurasi frozen")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    summary_path = SOURCE / "evaluation_metrics_summary.csv"
    ci_path = SOURCE / "evaluation_metrics_bootstrap_ci.csv"
    confusion_path = SOURCE / "evaluation_verdict_confusion.csv"
    status_path = SOURCE / "evaluation_verdict_status_cross_tab.csv"
    statuses_path = SOURCE / "evaluation_system_status_counts.csv"
    method_path = SOURCE / "evaluation_metrics_method.json"
    summary = read_csv(summary_path)
    ci = read_csv(ci_path)
    confusion = read_csv(confusion_path)
    status_cross = read_csv(status_path)
    statuses = read_csv(statuses_path)
    method = json.loads(method_path.read_text(encoding="utf-8-sig"))

    tables = {
        "metrik_160": summary,
        "bootstrap_ci_160": ci,
        "confusion_verdict": confusion,
        "silang_status_verdict": status_cross,
        "status_sistem": statuses,
    }
    for sheet, rows in tables.items():
        write_csv(OUTPUT / f"tabel_{sheet}.csv", rows)
    write_workbook(OUTPUT / "tabel_evaluasi_160.xlsx", tables)

    # CER/WER plot compares the three saved OCR text scopes for each condition.
    text_rows = [row for row in summary if row.get("level") in {"CER", "WER"}]
    scopes = ["teks_penuh", "komposisi", "lokal"]
    labels = {"teks_penuh": "Teks penuh", "komposisi": "Komposisi", "lokal": "Lokal"}
    for metric in ("CER", "WER"):
        fig, ax = plt.subplots(figsize=(9, 5.5))
        x = np.arange(len(scopes))
        width = 0.34
        for offset, condition, color in [(-width / 2, "datar", "#2a9d8f"), (width / 2, "melengkung", "#e9c46a")]:
            values = []
            for scope in scopes:
                row = next((r for r in text_rows if r["level"] == metric and r["cakupan"].casefold() == condition and r["kategori"] == scope), None)
                values.append(float(row["nilai"]) if row else 0.0)
            ax.bar(x + offset, values, width, label="Datar" if condition == "datar" else "Melengkung", color=color)
        ax.set_xticks(x, [labels[s] for s in scopes])
        ax.set_ylabel("Tingkat galat")
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=.2)
        fig.tight_layout()
        fig.savefig(OUTPUT / f"gambar_4_09_{metric.casefold()}_ocr_tiga_cakupan.png", dpi=300, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    matrix_rows = [r for r in confusion if r.get("cakupan") == "keseluruhan"]
    labels3 = ["aman", "perhatian", "hindari"]
    matrix = np.zeros((3, 3), dtype=int)
    for row in matrix_rows:
        if row["verdict_gt"] in labels3 and row["verdict_prediksi"] in labels3:
            matrix[labels3.index(row["verdict_gt"])][labels3.index(row["verdict_prediksi"])] = int(row["jumlah"])
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(3), ["Aman", "Perlu Perhatian", "Hindari"])
    ax.set_yticks(range(3), ["Aman", "Perlu Perhatian", "Hindari"])
    ax.set_xlabel("Verdict sistem")
    ax.set_ylabel("Verdict GT")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="black", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUTPUT / "gambar_4_11_confusion_verdict_160.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    inputs = [summary_path, ci_path, confusion_path, status_path, statuses_path, method_path, config_path]
    manifest = {
        "status": "final_160_evaluation_assets",
        "photos": 160,
        "config_status": config["status"],
        "threshold": config["threshold"],
        "metrics_method": method,
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "note": "Semua aset dihitung dari hasil tersimpan; tidak ada OCR, matcher, atau prediksi baru.",
    }
    (OUTPUT / "evaluation_160_assets_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive = ROOT / "evaluation/results/chapter4_assets_final.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(OUTPUT.iterdir()):
            if path.is_file() and not path.name.startswith("dryrun_"):
                bundle.write(path, arcname=f"chapter4/{path.name}")
    with zipfile.ZipFile(archive) as bundle:
        bad_member = bundle.testzip()
        if bad_member:
            raise RuntimeError(f"ZIP gagal diverifikasi: {bad_member}")
    print(f"Aset evaluasi 160 foto: {OUTPUT}")
    print(f"Paket terverifikasi: {archive} ({archive.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
