"""Summarize structured expert-interview responses against frozen GT/system labels.

``perlu_verifikasi`` and ``tidak_terbaca`` map to ``perhatian`` for 3-class
agreement, matching the frozen evaluation convention. Unanswered or invalid
expert verdicts are excluded pairwise and are counted in the output.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / "evaluation/results/expert_interview/case_key_research_only.csv"
CACHE = ROOT / "evaluation/results/evaluation_ocr/evaluation_predictions_cache.jsonl"
GT = ROOT / "evaluation/ground_truth/evaluation_gt_final.json"
VALID = {"aman", "perhatian", "hindari"}
SYSTEM_MAP = {"aman": "aman", "perhatian": "perhatian", "hindari": "hindari",
              "perlu_verifikasi": "perhatian", "tidak_terbaca": "perhatian"}


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " "))


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right): raise ValueError("Panjang label berpasangan harus sama.")
    if not left: return float("nan")
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum((left.count(k) / len(left)) * (right.count(k) / len(right)) for k in labels)
    return 1.0 if expected == 1 and observed == 1 else 0.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement_summary(left: list[str], right: list[str]) -> dict:
    n = len(left)
    return {"n_berpasangan": n, "persen_kesepakatan": 100 * sum(a == b for a, b in zip(left, right)) / n if n else None,
            "cohen_kappa": cohen_kappa(left, right) if n else None}


def likert_summary(values: list[int]) -> dict:
    ordered = sorted(values)
    if not ordered: return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    n = len(ordered); mid = n // 2
    median = ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {"n": n, "mean": sum(ordered) / n, "median": median, "min": ordered[0], "max": ordered[-1]}


def read_responses(path: Path):
    wb = load_workbook(path, data_only=True, read_only=True)
    def rows(sheet):
        it = sheet.iter_rows(values_only=True); headers = [str(x or "").strip() for x in next(it)]
        return [dict(zip(headers, row)) for row in it]
    verdict = {str(r.get("id_anonim", "")).strip(): r for r in rows(wb["verdict_ahli"])}
    presentation = {str(r.get("id_anonim", "")).strip(): r for r in rows(wb["penyajian_aplikasi"])}
    return verdict, presentation


def analyze(responses: Path, out_dir: Path = ROOT / "evaluation/results/expert_interview"):
    with KEY.open(encoding="utf-8-sig", newline="") as f: cases = list(csv.DictReader(f))
    gt = json.loads(GT.read_text(encoding="utf-8"))
    cache_rows = [json.loads(x) for x in CACHE.read_text(encoding="utf-8").splitlines() if x.strip()]
    pred = {r["filename"]: r["prediction"] for r in cache_rows if r.get("record_type") == "photo"}
    verdict_responses, ui_responses = read_responses(responses)
    metrics = []
    agreement_values = []
    scales = {k: [] for k in ("kejelasan_istilah_1_4", "urutan_informasi_1_4", "keterangan_konsumsi_1_4", "kelayakan_skrining_1_4")}
    for case in cases:
        filename, cid = case["filename"], case["id"]
        expert = norm(verdict_responses.get(cid, {}).get("verdict_ahli"))
        expert = expert.replace(" ", "_")
        system_raw = norm(pred[filename].get("classification", {}).get("verdict", pred[filename].get("verdict"))).replace(" ", "_")
        system = SYSTEM_MAP.get(system_raw)
        categories = {x["category"].casefold() for x in gt[filename].get("ingredients", [])}
        gt_label = "hindari" if "hindari" in categories else "perhatian" if "perhatian" in categories else "aman"
        metrics.append({"id": cid, "case_group": "acak_12" if case["case_type_research_only"] == "acak_berstrata" else "semua_16",
                        "gt": gt_label, "system": system, "expert": expert if expert in VALID else None})
        ui = ui_responses.get(cid, {})
        agreement = norm(ui.get("kesesuaian"))
        if agreement in {"sesuai", "sebagian", "tidak sesuai"}: agreement_values.append((cid, case["case_type_research_only"], agreement))
        for scale in scales:
            try: value = int(ui.get(scale))
            except (TypeError, ValueError): continue
            if value in (1, 2, 3, 4): scales[scale].append((cid, case["case_type_research_only"], value))

    rows = []
    for group_name, selected in (("acak_12", [r for r in metrics if r["case_group"] == "acak_12"]), ("semua_16", metrics)):
        for comparison, field in (("ahli_vs_sistem", "system"), ("ahli_vs_gt", "gt")):
            paired = [(r["expert"], r[field]) for r in selected if r["expert"] is not None and r[field] is not None]
            summary = agreement_summary([p[0] for p in paired], [p[1] for p in paired])
            rows.append({"cakupan": group_name, "analisis": comparison, **summary,
                         "n_tidak_terisi_atau_tidak_valid": len(selected) - len(paired)})
        cases_in = {r["id"] for r in selected}
        agr = [x[2] for x in agreement_values if x[0] in cases_in]
        for label in ("sesuai", "sebagian", "tidak sesuai"):
            rows.append({"cakupan": group_name, "analisis": f"proporsi_kesesuaian_{label}", "n": len(agr), "jumlah": agr.count(label), "proporsi": agr.count(label) / len(agr) if agr else None})
        for scale, vals in scales.items():
            subset = [x[2] for x in vals if x[0] in cases_in]
            rows.append({"cakupan": group_name, "analisis": f"skala_{scale}", **likert_summary(subset)})
        byid = {r["id"]: r for r in selected}
        bad = sum(r["gt"] == "hindari" and r["expert"] == "aman" for r in selected if r["expert"])
        rows.append({"cakupan": group_name, "analisis": "gt_hindari_dinilai_aman_oleh_ahli", "jumlah": bad})
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "expert_interview_analysis.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = list(dict.fromkeys(k for r in rows for k in r)); w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    (out_dir / "expert_interview_analysis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


def main():
    p = argparse.ArgumentParser(); p.add_argument("responses", type=Path, help="Workbook template yang sudah diisi ahli"); p.add_argument("--out-dir", type=Path, default=ROOT / "evaluation/results/expert_interview"); a = p.parse_args()
    print(json.dumps(analyze(a.responses, a.out_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
