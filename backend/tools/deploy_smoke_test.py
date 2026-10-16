"""Upload local photos to /identify and compare with frozen prediction cache.

Photos and interview ID mappings stay outside Git. An optional mapping CSV has
columns ``photo_file,cache_filename`` for anonymized W01-W16 photo names.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


def expected_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            if item.get("record_type") == "photo":
                rows[item["filename"]] = item["prediction"]
    if not rows:
        raise ValueError("Cache prediksi tidak berisi baris foto")
    return rows


def photo_map(folder: Path, mapping: Path | None) -> list[tuple[Path, str]]:
    if mapping:
        with mapping.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        photos = [(folder / row["photo_file"], row["cache_filename"]) for row in rows]
    else:
        photos = [(path, path.name) for path in sorted(folder.iterdir())
                  if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if not photos or any(not path.is_file() or path.parent.resolve() != folder.resolve()
                         for path, _ in photos):
        raise ValueError("Daftar foto kosong, hilang, atau keluar dari folder yang diminta")
    return photos


def post_photo(url: str, photo: Path, timeout: float) -> tuple[int, dict]:
    boundary = "lensalabel-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(photo.name)[0] or "application/octet-stream"
    payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"{photo.name}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
    payload += photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(url.rstrip("/") + "/identify", data=payload,
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                      method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        try:
            body = json.load(error)
        except ValueError:
            body = {"detail": "respons bukan JSON"}
        return error.code, body


def ingredients_from_api(data: dict) -> set[tuple[str, str]]:
    return {(str(item["standard_name"]), category)
            for category in ("aman", "perhatian", "hindari")
            for item in data.get(category, [])}


def ingredients_from_cache(data: dict) -> set[tuple[str, str]]:
    return {(str(item["standard_name"]), str(item["category"]))
            for item in data["entries"]}


def compare(actual: dict, expected: dict, http_status: int) -> dict:
    old, new = ingredients_from_cache(expected), ingredients_from_api(actual)
    return {
        "http_status": http_status,
        "missing_ingredients": json.dumps(sorted(old - new), ensure_ascii=False),
        "extra_ingredients": json.dumps(sorted(new - old), ensure_ascii=False),
        "expected_verdict": expected["verdict"],
        "actual_verdict": actual.get("verdict", ""),
        "expected_status": expected["classification"]["verdict"],
        "actual_status": actual.get("verdict", ""),
        "equal": http_status == 200 and old == new and
                 expected["verdict"] == actual.get("verdict"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Pilih lokasi CSV baru agar hasil lama tidak tertimpa")
    cached = expected_rows(args.expected)
    rows = []
    for photo, cache_name in photo_map(args.photos, args.mapping):
        if cache_name not in cached:
            raise KeyError(f"Tidak ada prediksi beku untuk {cache_name}")
        try:
            code, data = post_photo(args.url, photo, args.timeout)
            row = compare(data, cached[cache_name], code)
        except (OSError, URLError, ValueError) as error:
            row = {"http_status": "", "missing_ingredients": "", "extra_ingredients": "",
                   "expected_verdict": cached[cache_name]["verdict"],
                   "actual_verdict": "", "expected_status": cached[cache_name]["verdict"],
                   "actual_status": "", "equal": False, "error": str(error)}
        rows.append({"photo_file": photo.name, "cache_filename": cache_name,
                     "error": "", **row})
        print(f"{len(rows)}: {photo.name} {'cocok' if row['equal'] else 'BERBEDA'}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "photo_file", "cache_filename", "error", "http_status",
            "missing_ingredients", "extra_ingredients", "expected_verdict",
            "actual_verdict", "expected_status", "actual_status", "equal",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"photos": len(rows), "equal": sum(row["equal"] for row in rows),
                      "csv": str(args.output)}, ensure_ascii=False))
    if not all(row["equal"] for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
