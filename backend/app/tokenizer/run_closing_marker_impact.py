"""Compare old and current closing-marker extraction on existing transcripts.

This is a read-only sanity check. It does not modify the CSV or evaluation files.
Run from backend/:
  python -m app.tokenizer.run_closing_marker_impact
"""

from __future__ import annotations

import csv
import re
import zipfile
from xml.etree import ElementTree
from pathlib import Path

from rapidfuzz import fuzz

from app.tokenizer.tokenizer import extract_composition_section

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH_DIR = ROOT / "dataset" / "ground_truth"
OLD_CLOSE_MARKERS = ("MENGANDUNG ALERGEN", "ALLERGEN", "DIPRODUKSI", "MANUFACTURED")
OLD_THRESHOLD = 70


def old_find_marker(words: list[str], start: int = 0) -> int | None:
    for i in range(start, len(words)):
        for marker in OLD_CLOSE_MARKERS:
            width = len(marker.split())
            window = " ".join(words[i : i + width]).upper()
            if fuzz.ratio(marker, window) >= OLD_THRESHOLD:
                return i
    return None


def old_extract(text: str) -> str:
    words = text.split()
    open_markers = ("KOMPOSISI", "COMPOSITION", "INGREDIENTS")
    open_idx = None
    for i in range(len(words)):
        for marker in open_markers:
            width = len(marker.split())
            window = " ".join(words[i : i + width]).upper()
            if fuzz.ratio(marker, window) >= OLD_THRESHOLD:
                open_idx = i
                break
        if open_idx is not None:
            break
    if open_idx is None:
        return text
    close_idx = old_find_marker(words, start=open_idx + 1)
    return " ".join(words[open_idx:close_idx])


def read_xlsx(path: Path) -> list[dict[str, str]]:
    """Read the first worksheet from a simple XLSX file without writing to it."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{namespace}si"):
                shared_strings.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))

        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(f"{namespace}sheetData/{namespace}row"):
            values = {}
            for cell in row.findall(f"{namespace}c"):
                reference = cell.attrib["r"]
                column = re.sub(r"\d+", "", reference)
                value = cell.find(f"{namespace}v")
                raw = "" if value is None or value.text is None else value.text
                if cell.attrib.get("t") == "s":
                    raw = shared_strings[int(raw)]
                values[column] = raw
            rows.append(values)

    if not rows:
        return []
    headers = rows[0]
    return [
        {headers[column]: value for column, value in row.items() if column in headers}
        for row in rows[1:]
    ]


def load_ground_truth() -> list[dict[str, str]]:
    rows = []
    for path in sorted(GROUND_TRUTH_DIR.glob("transcripts_*.xlsx")):
        rows.extend(read_xlsx(path))
    return rows


def main() -> None:
    rows = load_ground_truth()
    candidates = [row for row in rows if "mengandung" in row["ground_truth_text"].lower()]
    differences = []

    for row in candidates:
        old_result = old_extract(row["ground_truth_text"])
        new_result = extract_composition_section(row["ground_truth_text"])
        if old_result != new_result:
            differences.append((row, old_result, new_result))

    print(f"Total transkripsi tersedia: {len(rows)}")
    print(f"Kandidat mengandung: {len(candidates)}")
    print(f"Hasil berbeda: {len(differences)}")
    for row, old_result, new_result in differences:
        print(f"\n{row['category']}/{row['filename']}")
        print(f"LAMA : {old_result}")
        print(f"BARU : {new_result}")


if __name__ == "__main__":
    main()
