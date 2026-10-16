
"""FMEA calculations and experimental risk-weight derivation."""

from __future__ import annotations

import csv
from pathlib import Path

FACTOR_FAILURE_MODES = {
    "safety": ("sterile indication", "warning text drift"),
    "device_class": (),
    "udi": ("wrong or missing udi", "expiry date mismatch"),
    "translation": ("required language missing", "translation"),
    "breadth": (),
    "markets": ("authorised representative",),
    "symbol": ("superseded symbol",),
    "defect_history": ("approval of an unverified draft",),
}


def load_fmea(path: str | Path) -> list[dict]:
    """Load FMEA rows and validate their numeric ratings."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise ValueError("The FMEA file contains no failure modes.")

    required = {
        "failure_mode",
        "severity",
        "occurrence",
        "detectability",
        "rpn",
    }
    if not required.issubset(rows[0]):
        missing = sorted(required - set(rows[0]))
        raise ValueError(f"Missing FMEA columns: {', '.join(missing)}")

    for row in rows:
        try:
            severity = int(row["severity"])
            occurrence = int(row["occurrence"])
            detectability = int(row["detectability"])
        except (TypeError, ValueError) as exc:
            raise ValueError("FMEA ratings must be integers.") from exc

        if any(value < 1 or value > 10
               for value in (severity, occurrence, detectability)):
            raise ValueError("FMEA ratings must be between 1 and 10.")

        expected_rpn = severity * occurrence * detectability
        if int(row["rpn"]) != expected_rpn:
            raise ValueError(
                f"Incorrect RPN for {row['failure_mode']!r}: "
                f"expected {expected_rpn}."
            )

        row["severity"] = severity
        row["occurrence"] = occurrence
        row["detectability"] = detectability
        row["rpn"] = expected_rpn

    return rows


def derive_weights(rows: list[dict]) -> dict:
    """Derive experimental weights from mapped failure modes using S x D.

    Ratings in the current FMEA CSV are draft estimates, not validated data.
    Factors without mapped failure modes retain equal baseline weights.
    """
    if not rows:
        raise ValueError("At least one FMEA row is required.")

    factor_scores = {}
    for factor, keywords in FACTOR_FAILURE_MODES.items():
        matching = [
            row for row in rows
            if any(keyword in row["failure_mode"].casefold()
                   for keyword in keywords)
        ]
        factor_scores[factor] = (
            sum(row["severity"] * row["detectability"] for row in matching)
            if matching else 1.0
        )

    total = sum(factor_scores.values())
    if total <= 0:
        raise ValueError("FMEA factor scores must have a positive total.")

    return {
        factor: round(value / total, 8)
        for factor, value in factor_scores.items()
    }


def calculate_rpn(severity: int, occurrence: int, detectability: int) -> int:
    """Return the conventional FMEA Risk Priority Number."""
    ratings = (severity, occurrence, detectability)
    if any(not isinstance(value, int) or isinstance(value, bool)
           or not 1 <= value <= 10 for value in ratings):
        raise ValueError("Severity, occurrence, and detectability must be integers from 1 to 10.")
    return severity * occurrence * detectability
