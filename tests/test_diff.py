import json

from tests.conftest import GEN, needs_data


@needs_data
def test_noise_pairs_report_no_change_and_edits_detected():
    from engines.diff import diff

    truth = json.loads((GEN / "diff_truth.json").read_text())
    for p in truth:
        a, b = GEN / p["approved"], GEN / p["revised"]
        r = diff(a / "label.pdf", b / "label.pdf", a / "label.png", b / "label.png")
        if p["noise_only"]:
            assert r["changes"] == [], p["pair_id"]
        else:
            assert r["changes"], p["pair_id"]
