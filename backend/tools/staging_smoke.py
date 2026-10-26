"""Check a running deployment with one real photo and report HTTP latency."""

import argparse
import json
import mimetypes
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Public frontend URL")
    parser.add_argument("--photo", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    base = args.url.rstrip("/")

    for endpoint in ("/health", "/ready"):
        started = perf_counter()
        with urlopen(base + endpoint, timeout=args.timeout) as response:
            data = json.load(response)
            assert response.status == 200 and data["status"] == "ok", data
        print(f"{endpoint}: {perf_counter() - started:.2f}s, KB {data['kb_version']}")

    boundary = "lensalabel-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(args.photo.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{args.photo.name}\"\r\nContent-Type: {mime}\r\n\r\n"
    ).encode() + args.photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(
        base + "/identify",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    started = perf_counter()
    with urlopen(request, timeout=args.timeout) as response:
        data = json.load(response)
        assert response.status == 200 and data["verdict"] in {
            "aman", "perhatian", "hindari", "perlu_verifikasi", "tidak_terbaca"
        }, data
    print(f"/identify: {perf_counter() - started:.2f}s, verdict {data['verdict']}")


if __name__ == "__main__":
    main()
