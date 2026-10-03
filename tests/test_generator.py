import json
from datetime import date

import jsonschema

from generator.label_generator import add_months, build_spec, render
from tests.conftest import GEN, needs_data


def test_add_months_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 9, 15), 36) == date(2029, 9, 15)


def test_deterministic_json_and_pdf(tmp_path):
    a = build_spec("CS-100", "EU", "carton", seed=42)
    b = build_spec("CS-100", "EU", "carton", seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    pa = render(a, tmp_path / "a", png=False)
    pb = render(b, tmp_path / "b", png=False)
    assert open(pa["pdf"], "rb").read() == open(pb["pdf"], "rb").read()
    assert open(pa["json"], "rb").read() == open(pb["json"], "rb").read()


def test_eu_label_has_required_languages_and_ec_rep():
    s = build_spec("CS-200", "EU", "carton")
    langs = {e["language"] for e in s["elements"] if e.get("zone") == "languages"}
    assert langs == {"en", "de", "fr"}
    assert any(e["element"] == "authorised_rep" for e in s["elements"])
    us = build_spec("CS-200", "US", "carton")
    assert not any(e["element"] == "authorised_rep" for e in us["elements"])
    assert any(e["element"] == "rx_statement" for e in us["elements"])


TRUTH_SCHEMA = {"type": "array", "items": {"type": "object", "required": ["label_id", "base_label_id", "defects"],
                                           "properties": {"defects": {"type": "array", "minItems": 1, "items": {
                                               "type": "object", "required": ["defect_id", "element", "bbox_mm",
                                                                              "expected_rule", "severity"]}}}}}


@needs_data
def test_ground_truth_validates():
    gt = json.loads((GEN / "ground_truth.json").read_text())
    jsonschema.validate(gt, TRUTH_SCHEMA)
    types = {d["defect_id"] for g in gt for d in g["defects"]}
    assert types == {f"D{i:02d}" for i in range(1, 15)}
    clean = json.loads((GEN / "clean_set.json").read_text())
    assert len(clean["holdout_clean"]) == 30
