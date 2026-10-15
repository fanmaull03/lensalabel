import csv
import json

import pytest

run_grid_search = pytest.importorskip("evaluation.run_grid_search")


@pytest.mark.parametrize('mode,expected_tp', [('old', 1), ('many', 2), ('many_shared', 2)])
def test_grid_uses_selected_matcher(tmp_path, monkeypatch, mode, expected_tp):
    (tmp_path / 'split.csv').write_text('filename,category\nexample.jpeg,datar\n')
    kb = [dict(ingredient_id=i, standard_name=n, name_variant=n, category='aman')
          for i, n in enumerate(['Garam', 'Gula'])]
    (tmp_path / 'kb.json').write_text(json.dumps(kb))
    (tmp_path / 'gt.json').write_text(json.dumps({'example.jpeg': {'ingredients': kb}}))
    (tmp_path / 'example.jpeg.json').write_text(json.dumps(dict(
        filename='example.jpeg', detections=[dict(
            bbox=[[0, 0], [100, 0], [100, 20], [0, 20]], text='Garam Gula', confidence=.99)])))
    monkeypatch.setattr('sys.argv', [
        'run_grid_search.py', '--split-csv', str(tmp_path / 'split.csv'),
        '--cache-dir', str(tmp_path), '--kb-json', str(tmp_path / 'kb.json'),
        '--ground-truth-json', str(tmp_path / 'gt.json'), '--matcher', mode,
        '--detail-csv', str(tmp_path / 'detail.csv'), '--summary-csv', str(tmp_path / 'summary.csv'),
    ])
    run_grid_search.main()
    rows = list(csv.DictReader((tmp_path / 'summary.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 6
    assert all(int(r['tp']) == expected_tp and int(r['fp']) == 0 and int(r['fn']) == 2 - expected_tp for r in rows)
