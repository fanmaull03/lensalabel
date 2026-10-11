"""Export the runtime knowledge base to a portable JSON snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.matching.fuzzy_matcher import load_knowledge_base  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evaluation/kb_snapshot.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        kb = load_knowledge_base(session)
    args.output.write_text(json.dumps(kb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(kb)} variants to {args.output}")


if __name__ == "__main__":
    main()
