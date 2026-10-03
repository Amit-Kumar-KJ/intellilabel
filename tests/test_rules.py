"""One failing and one passing label per rule (failing labels come from the seeded defect set)."""
import json

import pytest

from core import master as M
from engines.compliance import validate_file
from tests.conftest import GEN, needs_data


def _first_per_defect():
    gt = json.loads((GEN / "ground_truth.json").read_text())
    seen = {}
    for g in gt:
        d = g["defects"][0]
        seen.setdefault(d["defect_id"], (g["label_id"], d["expected_rule"]))
    return sorted(seen.values())


@needs_data
@pytest.mark.parametrize("label_id,rule", _first_per_defect() if (GEN / "ground_truth.json").exists() else [])
def test_rule_fires_on_defect(label_id, rule):
    spec = json.loads((GEN / "defective" / label_id / "label.json").read_text())
    rep = validate_file(GEN / "defective" / label_id / "label.pdf", spec, reqs=M.requirements())
    assert rule in {f["rule_id"] for f in rep["findings"]}
    sev = {f["severity"] for f in rep["findings"] if f["rule_id"] == rule}
    assert rep["status"] in ("FAIL", "REVIEW") or sev == {"minor"}  # minor findings do not block


@needs_data
def test_clean_labels_pass():
    clean = json.loads((GEN / "clean_set.json").read_text())["holdout_clean"][:6]
    for lid in clean:
        spec = json.loads((GEN / "clean" / lid / "label.json").read_text())
        rep = validate_file(GEN / "clean" / lid / "label.pdf", spec, reqs=M.requirements())
        assert rep["status"] == "PASS", (lid, rep["findings"])


@needs_data
def test_extractor_never_reads_label_json(monkeypatch, tmp_path):
    import shutil

    lid = json.loads((GEN / "clean_set.json").read_text())["holdout_clean"][0]
    shutil.copy(GEN / "clean" / lid / "label.pdf", tmp_path / "label.pdf")  # no json next to it
    from engines.extraction import extract

    m = extract(tmp_path / "label.pdf")
    assert m["barcodes"] and m["elements"].get("udi_hri")
