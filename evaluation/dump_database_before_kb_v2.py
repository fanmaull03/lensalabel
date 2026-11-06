"""Create and verify a full custom-format PostgreSQL dump before KB v2 writes."""
from __future__ import annotations

import json
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy.engine import make_url  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-user", help="Role used only for this backup (never printed).")
    args = parser.parse_args()
    pg_dump = shutil.which("pg_dump") or r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
    pg_restore = shutil.which("pg_restore") or r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe"
    if not Path(pg_dump).is_file() or not Path(pg_restore).is_file():
        raise SystemExit("pg_dump dan pg_restore harus tersedia sebelum Fase 3.")

    url = make_url(settings.DATABASE_URL)
    if not url.database:
        raise SystemExit("DATABASE_URL tidak memuat nama database.")
    db_env = os.environ.copy()
    if url.host:
        db_env["PGHOST"] = url.host
    if url.port:
        db_env["PGPORT"] = str(url.port)
    db_user = args.db_user or url.username
    if db_user:
        db_env["PGUSER"] = db_user
    if url.password and not args.db_user:
        db_env["PGPASSWORD"] = url.password
    db_env["PGDATABASE"] = url.database
    for key in ("sslmode", "sslcert", "sslkey", "sslrootcert", "connect_timeout"):
        value = url.query.get(key)
        if value:
            env_key = "PG" + key.upper()
            db_env[env_key] = str(value)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = ROOT / "archive/db_dumps"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_path = backup_dir / f"lensalabel_pre_kb_v2_{stamp}.dump"
    dump_cmd = [pg_dump, "--format=custom", "--file", str(dump_path), "--dbname", url.database]
    result = subprocess.run(dump_cmd, env=db_env, capture_output=True, text=True)
    if result.returncode != 0:
        dump_path.unlink(missing_ok=True)
        detail = result.stderr
        if url.password:
            detail = detail.replace(url.password, "[REDACTED]")
        if url.username:
            detail = detail.replace(url.username, "[DB_USER]")
        raise SystemExit(f"pg_dump gagal dengan exit code {result.returncode}; dump tidak dipakai.\n{detail.strip()}")
    if not dump_path.exists() or dump_path.stat().st_size == 0:
        raise SystemExit("pg_dump tidak menghasilkan file penuh yang valid.")

    listing = subprocess.run(
        [pg_restore, "--list", str(dump_path)],
        env=db_env, capture_output=True, text=True,
    )
    if listing.returncode != 0 or not listing.stdout.strip():
        raise SystemExit("pg_restore --list gagal; jangan lanjut ke perubahan database.")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "format": "PostgreSQL custom archive; complete database schema and data",
        "path": str(dump_path.relative_to(ROOT)),
        "size_bytes": dump_path.stat().st_size,
        "verified_with_pg_restore_list": True,
        "database_name": url.database,
    }
    manifest_path = dump_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
