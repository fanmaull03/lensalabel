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

Alembic dijalankan dengan interpreter yang sama agar menggunakan environment DB dan modul proyek yang tervalidasi:

```powershell
.\backend\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

Simpan kondisi paket untuk reproduksibilitas dengan:

```powershell
.\backend\.venv\Scripts\python.exe -m pip freeze
```

Snapshot untuk eksperimen 2026-10-10 ada di `evaluation/results/environment_freeze.txt`.


Grafik eksperimen lokal memerlukan `matplotlib`, yang dicatat bersama `pytest` pada `requirements-dev.txt`.
