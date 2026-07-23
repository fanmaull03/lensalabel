"""Sinkronkan sinonim baru dari DRAFT_INGREDIENTS ke database yang sudah jalan.

Beda dengan seed_knowledge_base.py yang melewati bahan yang sudah ada: script
ini khusus menambal sinonim yang belum ada pada bahan yang SUDAH ada, tanpa
menyentuh baris ingredient-nya sama sekali. Aman dijalankan berulang.

Sengaja hanya INSERT, tidak pernah UPDATE atau DELETE: kalau ada sinonim di
database yang tidak ada di file seed, itu diasumsikan hasil penyuntingan manual
dan dibiarkan (cuma dilaporkan). Perbandingan case-insensitive supaya 'Salt'
tidak dobel dengan 'salt'.

Cara pakai (dari folder backend/):
  python -m app.db.sync_synonyms          # lihat rencana, tidak menulis apa pun
  python -m app.db.sync_synonyms --apply  # benar-benar insert
"""

from __future__ import annotations

import sys

from app.db.models import Ingredient, IngredientSynonym
from app.db.seed_knowledge_base import DRAFT_INGREDIENTS
from app.db.session import SessionLocal


def sync(apply: bool) -> None:
    with SessionLocal() as session:
        rencana: list[tuple[str, str]] = []
        hanya_di_db: list[tuple[str, str]] = []

        for standard_name, synonyms, _, _ in DRAFT_INGREDIENTS:
            ingredient = (
                session.query(Ingredient).filter_by(standard_name=standard_name).first()
            )
            if ingredient is None:
                print(f"  ! '{standard_name}' belum ada di database, dilewati "
                      f"(jalankan seed_knowledge_base dulu).")
                continue

            existing = {s.synonym.lower() for s in ingredient.synonyms}
            for syn in synonyms:
                if syn.lower() in existing:
                    continue
                rencana.append((standard_name, syn))
                if apply:
                    ingredient.synonyms.append(IngredientSynonym(synonym=syn))

            dari_seed = {s.lower() for s in synonyms}
            hanya_di_db += [
                (standard_name, s.synonym)
                for s in ingredient.synonyms
                if s.synonym.lower() not in dari_seed
            ]

        if hanya_di_db:
            print("Sinonim yang ada di database tapi tidak di file seed (dibiarkan):")
            for nama, syn in hanya_di_db:
                print(f"  {nama}: {syn!r}")

        if not rencana:
            print("Tidak ada sinonim baru. Database sudah sinkron dengan file seed.")
            return

        print(f"\n{len(rencana)} sinonim baru{'' if apply else ' (rencana, belum ditulis)'}:")
        for nama, syn in rencana:
            print(f"  + {nama:24} <- {syn!r}")

        if apply:
            session.commit()
            print(f"\nSelesai. {len(rencana)} sinonim ditambahkan.")
        else:
            print("\nJalankan ulang dengan --apply untuk menulis ke database.")


if __name__ == "__main__":
    sync(apply="--apply" in sys.argv)
