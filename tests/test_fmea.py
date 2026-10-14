from pathlib import Path

import pytest

from core.config import ROOT
from core.fmea import calculate_rpn, derive_weights, load_fmea


def test_load_fmea_rows():
    rows = load_fmea(ROOT / "docs" / "fmea.csv")

    assert len(rows) == 10
    assert all(row["rpn"] == row["severity"] * row["occurrence"] * row["detectability"] for row in rows)


def test_derive_weights_sum_to_one():
    rows = load_fmea(ROOT / "docs" / "fmea.csv")
    weights = derive_weights(rows)

    assert set(weights) == {
        "safety",
        "device_class",
        "udi",
        "translation",
        "breadth",
        "markets",
        "symbol",
        "defect_history",
    }
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(weight >= 0 for weight in weights.values())


def test_calculate_rpn():
    assert calculate_rpn(8, 4, 6) == 192
    assert calculate_rpn(10, 10, 10) == 1000


@pytest.mark.parametrize(
    "ratings",
    [
        (0, 5, 5),
        (5, 11, 5),
        (5, 5, 0),
        (1.5, 5, 5),
    ],
)
def test_calculate_rpn_rejects_invalid_ratings(ratings):
    with pytest.raises(ValueError):
        calculate_rpn(*ratings)