"""Create a cache-only Colab experiment; never includes evaluation photos."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'evaluation/results/gt_matcher_revision'


def main():
    names = [
        'backend/app/__init__.py', 'backend/app/db/__init__.py', 'backend/app/db/models.py',
        'backend/app/matching/__init__.py', 'backend/app/matching/fuzzy_matcher.py',
        'backend/app/matching/secondary_guards.py',
        'backend/app/classifier/__init__.py', 'backend/app/classifier/rule_based.py',
        'backend/app/ocr/__init__.py', 'backend/app/ocr/reader.py',
        'backend/app/tokenizer/__init__.py', 'backend/app/tokenizer/tokenizer.py',
        'backend/tests/test_multi_matcher.py', 'backend/tests/test_fuzzy_matcher.py',
        'backend/tests/test_negation_matching.py', 'backend/tests/test_rule_based.py',
        'backend/tests/test_grid_matcher_modes.py',
        'backend/tests/test_tokenizer.py', 'backend/tests/test_reader.py',
        'evaluation/compare_gt_matchers.py', 'evaluation/run_grid_search.py',
        'evaluation/kb_snapshot.json', 'evaluation/splits/calibration_set.csv',
        'dataset/ground_truth/calibration_ingredients_gt_final.json',
        'dataset/ground_truth/correction_history/20261006_145456_transcript_mapping/calibration_ingredients_gt_final.json',
        'evaluation/results/colab_v4/grid_detail.csv',
    ]
    split = list(csv.DictReader((ROOT / 'evaluation/splits/calibration_set.csv').open(encoding='utf-8-sig')))
    assert len(split) == 40
    gt = json.loads((ROOT / 'dataset/ground_truth/calibration_ingredients_gt_final.json').read_text(encoding='utf-8'))
    assert set(gt) == {r['filename'] for r in split}
    for row in split:
        names.append(f"evaluation/results/colab_v4/ocr_cache/{row['filename']}.json")
    manifest = dict(photos=40, ocr_rerun=False,
                    new_gt_ingredients=sum(len(v['ingredients']) for v in gt.values()),
                    sha256={n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names})
    bundle = OUTPUT / 'lensalabel_gt_matcher_comparison_bundle.zip'
    with ZipFile(bundle, 'w', ZIP_DEFLATED) as z:
        for name in names:
            z.write(ROOT / name, name)
        z.writestr('bundle_manifest.json', json.dumps(manifest, indent=2))
    with ZipFile(bundle) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest() == digest for n, digest in manifest['sha256'].items())

    def markdown(text):
        return dict(cell_type='markdown', metadata={}, source=text.splitlines(keepends=True))

    def code(text):
        return dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=text.splitlines(keepends=True))

    cells = [markdown('''# Perbandingan koreksi GT dan matcher

Unggah `lensalabel_gt_matcher_comparison_bundle.zip`, lalu **Run all**.
40 cache OCR mentah tersedia dalam ZIP; tidak perlu foto atau OCR ulang.
CPU cukup: matching ini tidak memakai GPU. Split, KB, reading-order, closing-marker dan bobot tetap.

Empat kondisi: (a) GT lama + matcher lama, (b) GT baru + matcher lama,
(c) GT baru + multi-match/kepala bersama, serta ablasi multi-match tanpa kepala bersama.
Threshold 70/75/80/85/90/95. Prediksi (a) diverifikasi terhadap 240 baris hasil Colab sebelumnya.
Hasil tidak mengubah threshold produksi otomatis.
'''), code('''from pathlib import Path
import os, json, hashlib, platform, subprocess, sys, zipfile
from datetime import datetime, timezone
from google.colab import files

uploaded = files.upload()
archives = [name for name in uploaded if name.endswith('.zip')]
assert len(archives) == 1, 'Unggah satu ZIP bundle eksperimen.'
root = Path('/content/lensalabel_gt_matcher_comparison')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(archives[0]) as z:
    assert all((root / n).resolve().is_relative_to(root.resolve()) for n in z.namelist())
    z.extractall(root)
os.chdir(root)
manifest = json.loads(Path('bundle_manifest.json').read_text())
for name, digest in manifest['sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
print('Bundle terverifikasi:', manifest['photos'], 'foto;', manifest['new_gt_ingredients'], 'anotasi GT baru')
'''), code('''subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'rapidfuzz==3.14.5', 'SQLAlchemy>=2.0,<2.1', 'opencv-python-headless>=4.10', 'pytest>=8'], check=True)
env = dict(os.environ, PYTHONPATH=str(root / 'backend') + ':' + str(root))
subprocess.run([sys.executable, '-m', 'pytest', 'backend/tests', '-q'], env=env, check=True)
'''), code('''output = Path('evaluation/results/gt_matcher_revision_colab')
output.mkdir(parents=True, exist_ok=True)
runtime = {'utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version, 'platform': platform.platform(), 'source': 'Colab', 'ocr_rerun': False}
(output / 'runtime.json').write_text(json.dumps(runtime, indent=2))
(output / 'pip_freeze.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
command = [sys.executable, '-u', 'evaluation/compare_gt_matchers.py',
    '--old-gt', 'dataset/ground_truth/correction_history/20261006_145456_transcript_mapping/calibration_ingredients_gt_final.json',
    '--new-gt', 'dataset/ground_truth/calibration_ingredients_gt_final.json',
    '--cache-dir', 'evaluation/results/colab_v4/ocr_cache',
    '--historical-detail', 'evaluation/results/colab_v4/grid_detail.csv',
    '--output-dir', str(output)]
with (output / 'run.log').open('w') as log:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    for line in process.stdout:
        print(line, end='')
        log.write(line)
    if process.wait():
        raise RuntimeError('Eksperimen gagal; lihat run.log, jangan gunakan hasil parsial.')
'''), code('''from IPython.display import Markdown, display
assert json.loads((output / 'run_manifest.json').read_text())['complete']
display(Markdown((output / 'comparison_report.md').read_text()))
archive = Path('/content/lensalabel_gt_matcher_comparison_results.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in output.rglob('*'):
        if path.is_file():
            z.write(path, path.relative_to(Path('evaluation/results')))
files.download(str(archive))
'''), markdown('''Ekstrak ZIP hasil ke `D:\\Kulyeah\\SKRIPSI\\project\\lensalabel\\evaluation\\results`.
Hasil akan berada di `gt_matcher_revision_colab/`. Hasil grid lama tetap tersimpan terpisah.
''')]
    notebook = dict(cells=cells, metadata=dict(kernelspec=dict(display_name='Python 3', language='python', name='python3'), language_info=dict(name='python')), nbformat=4, nbformat_minor=5)
    for i, cell in enumerate(cells):
        cell['id'] = f'comparison_{i}'
        if cell['cell_type'] == 'code':
            compile(''.join(cell['source']), f'cell_{i}', 'exec')
    path = ROOT / 'evaluation/notebooks/gt_matcher_comparison_colab.ipynb'
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{bundle}: {bundle.stat().st_size / 1024**2:.2f} MiB; {len(names)} verified files')
    print(path)


if __name__ == '__main__':
    main()
