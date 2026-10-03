# Risk weights (Phase 10)

Risk = sum of weight x factor (each factor 0-1, weights sum to 1). Tiers: < 0.3 Low, 0.3-0.7 Medium, > 0.7 High.
Hard override: an open critical finding on a safety-related element makes the tier High.

| Factor | How computed | Current weight | FMEA failure modes it represents (S x D) |
|---|---|---|---|
| safety | any changed key/element is a warning, sterilization, MR or storage element | 0.30 | warning drift, sterile indication |
| device_class | 1 for Class III, 0.5 Class II/IIb | 0.15 | - |
| udi | any UDI element changes | 0.10 | wrong UDI, expiry mismatch |
| translation | share of impacted labels with re-validated translations | 0.10 | language missing, translation drift |
| breadth | impacted labels / current labels | 0.10 | - |
| markets | impacted markets / active markets | 0.10 | missing EC REP |
| symbol | any symbol added, removed or swapped | 0.05 | superseded symbol |
| defect_history | share of past changes with critical findings | 0.10 | approval of unverified draft |

**To do after the FMEA is validated:** set each weight in proportion to severity x detectability of the failure modes
it represents, write them to `docs/risk_weights.json` (the app loads that file automatically and renormalises), and
re-run `make bench` to refresh the sensitivity table (`eval/results/risk_sensitivity.json`).
