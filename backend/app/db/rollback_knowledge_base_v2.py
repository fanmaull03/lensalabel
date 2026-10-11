"""Restore the database from the full pre-KB-v2 custom-format pg_dump.

This is intentionally destructive and therefore requires an explicit --apply.
It restores into an already-created database; it does not drop the database.
"""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DUMP = ROOT / "archive/db_dumps/lensalabel_pre_kb_v2_20261009T113811Z.dump"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Existing target database name")
    parser.add_argument("--apply", action="store_true", help="Actually restore and replace existing objects")
    args = parser.parse_args()
    if not DUMP.is_file():
        raise SystemExit(f"Database dump not found: {DUMP}")
    command = [
        "pg_restore", "--clean", "--if-exists", "--no-owner", "--exit-on-error",
        f"--dbname={args.database}", str(DUMP),
    ]
    if not args.apply:
        print("Dry run; command that would execute:")
        print(subprocess.list2cmdline(command))
        return
    subprocess.run(command, check=True, env=os.environ.copy())
    print(f"Restored database {args.database!r} from {DUMP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
