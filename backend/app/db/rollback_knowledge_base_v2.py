"""Restore the database from the full pre-KB-v2 custom-format pg_dump.

This is intentionally destructive and therefore requires an explicit --apply.
It restores into an already-created database; it does not drop the database.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import settings


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DUMP = ROOT / "archive/db_dumps/lensalabel_pre_kb_v2_20261009T113811Z.dump"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Existing target database name")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP,
                        help="Full custom-format pg_dump to restore (default: original pre-v2 dump)")
    parser.add_argument("--apply", action="store_true", help="Actually restore and replace existing objects")
    args = parser.parse_args()
    dump = args.dump.resolve()
    if not dump.is_file():
        raise SystemExit(f"Database dump not found: {dump}")
    pg_restore = shutil.which("pg_restore") or r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe"
    if not Path(pg_restore).is_file():
        raise SystemExit("pg_restore tidak tersedia.")
    url = make_url(settings.DATABASE_URL)
    db_env = os.environ.copy()
    if url.host:
        db_env["PGHOST"] = url.host
    if url.port:
        db_env["PGPORT"] = str(url.port)
    if url.username:
        db_env["PGUSER"] = url.username
    if url.password:
        db_env["PGPASSWORD"] = url.password
    command = [
        pg_restore, "--clean", "--if-exists", "--no-owner", "--exit-on-error",
        f"--dbname={args.database}", str(dump),
    ]
    if not args.apply:
        print("Dry run; command that would execute:")
        print(subprocess.list2cmdline(command))
        return
    subprocess.run(command, check=True, env=db_env)
    print(f"Restored database {args.database!r} from {dump}")


if __name__ == "__main__":
    main()
