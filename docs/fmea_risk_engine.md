# FMEA-Based Risk Engine

## Overview

The FMEA module provides utilities for validating Failure Mode and Effects Analysis (FMEA) data, calculating Risk Priority Numbers (RPNs), and deriving experimental risk-factor weights.

## Features

- Loads FMEA records from a CSV file.
- Validates severity, occurrence, and detectability ratings.
- Checks whether each RPN equals severity × occurrence × detectability.
- Derives normalized experimental weights for mapped risk factors.
- Calculates RPN values for individual failure modes.
- Rejects invalid ratings outside the range of 1–10.

## Risk Priority Number

The Risk Priority Number is calculated as:

RPN = Severity × Occurrence × Detectability

Each rating must be an integer between 1 and 10.

## Weight Derivation

The module uses severity × detectability to estimate relative factor importance from mapped failure modes. Factors without mapped failure modes retain a baseline score.

The resulting weights are normalized so that their total is approximately 1.

## Data Limitations

The current records in `docs/fmea.csv` contain draft estimates. The derived weights are experimental and must not be treated as validated clinical, safety, or regulatory risk parameters.

Failure-mode mappings and ratings should be reviewed by qualified domain experts before production use.

## Testing

Run the focused tests:

`python -m pytest tests/test_fmea.py -v`

Run the complete test suite:

`python -m pytest -q`