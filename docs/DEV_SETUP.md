# Developer setup (Windows)

Gunakan virtual environment proyek di `backend/.venv`. Interpreter terverifikasi:

```powershell
.\backend\.venv\Scripts\python.exe
```

Versi yang dipakai saat validasi: Python 3.12; interpreter ini lolos impor `rapidfuzz`, `cv2`, `sqlalchemy`, `openpyxl`, `alembic`, `fastapi`, dan `pytest`.

Jalankan suite backend dan evaluasi dari root repository:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests evaluation/tests -q
```

Dependensi aplikasi dipasang dari `backend/requirements.txt`; runner tes dicatat di `requirements-dev.txt`:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\backend\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Jalankan Alembic dari `backend/` agar `app.config` membaca `backend/.env`, bukan URL contoh bawaan. Gunakan interpreter yang sama:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

Simpan kondisi paket untuk reproduksibilitas dengan:

```powershell
.\backend\.venv\Scripts\python.exe -m pip freeze
```

Snapshot untuk eksperimen 2026-10-10 ada di `evaluation/results/environment_freeze.txt`.


Grafik eksperimen lokal memerlukan `matplotlib`, yang dicatat bersama `pytest` pada `requirements-dev.txt`.

## Memuat KB v2 hasil validasi ahli ke database aplikasi

Runtime API mengambil bahan dari tabel PostgreSQL `ingredients` dan `ingredient_synonyms`; berkas KB v2 tidak dibaca langsung saat permintaan identifikasi. Sumber v2 yang dipakai evaluasi adalah `evaluation/results/kb_v2_phase2/kb_v2_review.json` dan hash-nya tercatat di `evaluation/config_frozen.json`. Pada database baru, buat dump penuh sebelum seed, lalu jalankan perintah berikut dari root repo:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe ..\evaluation\dump_database_before_kb_v2.py
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.seed_knowledge_base_v2 --apply
Pop-Location
```

Periksa bahwa dump di `archive/db_dumps/` lolos `pg_restore --list`. Dump dan `.env` bersifat lokal; jangan dikomit. Seed v2 semestinya menghasilkan 259 bahan, 1.030 sinonim, dan 264 catatan validasi. Jangan menjalankan `python -m app.db.seed_knowledge_base` setelahnya: skrip itu memakai KB 240 entri lama dan akan menyinkronkan database kembali ke v1.

Bandingkan seluruh varian yang benar-benar dipakai matcher, beserta ID, nama, dan kategori, dengan KB v2 yang tercatat di konfigurasi beku. Dari root repo:

```powershell
Push-Location backend
@'
import hashlib, json, sys
from pathlib import Path
from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.db.models import Ingredient, IngredientSynonym, ExpertValidation
from app.matching.fuzzy_matcher import load_knowledge_base
root = Path('..').resolve()
sys.path.insert(0, str(root))
from evaluation.run_evaluate_160_parallel import flatten_kb
config = json.loads((root / 'evaluation/config_frozen.json').read_text(encoding='utf-8'))
source = root / config['kb_path']
assert hashlib.sha256(source.read_bytes()).hexdigest() == config['kb_sha256']
expected, _, _ = flatten_kb(json.loads(source.read_text(encoding='utf-8')))
canonical = lambda rows: sorted((int(row['ingredient_id']), row['standard_name'], row['category'], row['name_variant']) for row in rows)
with SessionLocal() as db:
    actual = load_knowledge_base(db)
    counts = tuple(db.scalar(select(func.count()).select_from(model)) for model in (Ingredient, IngredientSynonym, ExpertValidation))
assert counts == (259, 1030, 264), counts
assert len(actual) == len(expected) == 1289
assert canonical(actual) == canonical(expected), 'Varian database tidak sama dengan KB evaluasi'
print('KB v2 identik:', counts, 'tabel; 1289 varian matcher')
'@ | .\.venv\Scripts\python.exe -
Pop-Location
```

`backend/app/db/rollback_knowledge_base_v2.py` menerima `--dump` untuk memilih dump penuh yang dibuat tepat sebelum seed. Tanpa `--apply`, skrip hanya menampilkan rencana pemulihan; pemulihan penuh mengganti isi database dan tidak termasuk langkah setup rutin.
