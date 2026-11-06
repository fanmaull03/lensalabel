import json

import pytest

from evaluation.recompute_ablation_metrics import local_cer_wer, normalize_for_metrics
from evaluation.frozen_config import load_config


def test_local_errors_ignore_only_outer_ocr_text():
    gt = normalize_for_metrics("Komposisi: Susu sapi")
    exact_with_noise = normalize_for_metrics("nutrition facts Komposisi: Susu sapi takaran saji")
    typo_with_noise = normalize_for_metrics("nutrition facts Komposisi: Susu saqi takaran saji")

    assert local_cer_wer(gt, exact_with_noise) == (0.0, 0.0)
    cer, wer = local_cer_wer(gt, typo_with_noise)
    assert cer == pytest.approx(1 / len(gt))
    assert wer == pytest.approx(1 / len(gt.split()))


def test_draft_config_blocks_final_workflows(tmp_path, monkeypatch):
    config = load_config()
    config["status"] = "draft"
    draft_path = tmp_path / "config_draft.json"
    draft_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr("evaluation.frozen_config.CONFIG_PATH", draft_path)
    assert config["status"] == "draft"
    with pytest.raises(RuntimeError, match="harus 'frozen'"):
        load_config(require_frozen=True)
