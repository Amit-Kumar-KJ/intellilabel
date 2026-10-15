# Assumptions register

Every number shown in the deck or the app goes here with its basis. "Measured" numbers link to a file in
`eval/results/` (regenerate with `make bench`). Replace "our estimate" with interview-based values as you get them.

| # | Value | Unit | Basis | Source / file | Owner |
|---|---|---|---|---|---|
| A01 | 3 | SKUs | Hero family definition | docs/scope.md | Amit |
| A02 | 18 | released label variants (US+EU) | 3 SKUs x 2 markets x 3 packaging levels | data/generated/variant_matrix.json | Amit |
| A03 | 36 | label variants per revision incl. planned JP/CN | 3 SKUs x 4 markets x 3 levels | eval/results/variant_matrix.json | Amit |
| A04 | 18 of 18 | labels impacted by Scenario A | measured (impact engine) | tests/test_graph_workflow.py | Amit |
| A05 | 6 of 18 | labels non-compliant in Scenario B | measured (rule R20 on EU pouch + carton) | tests/test_graph_workflow.py | Amit |
| A06 | 126 | defective labels (14 types x 9) | generator, seed 42 | data/generated/ground_truth.json | Amit |
| A07 | 30 | clean holdout labels for false-positive rate | generator, seed 42 | data/generated/clean_set.json | Amit |
| A08 | see file | Tier 1 recall / precision / clean FP rate | measured, seen defects (upper bound) | eval/results/compliance_tier1.json | Amit |
| A09 | see file | diff detection / classification / noise false alarms | measured on 13 pairs | eval/results/diff_results.json | Amit |
| A10 | see file | translation validator precision / recall | measured on 44 cases (seen) | eval/results/translation_results.json | Amit |
| A11 | 10/10 | ledger tamper detection | measured | eval/results/ledger_results.json | Amit |
| A12 | see file | robustness recall on degraded images | measured, 8 labels x 4 conditions | eval/results/robustness.json | Amit |
| A13 | 0.30/0.15/0.10/0.10/0.10/0.10/0.05/0.10 | risk weights | guide defaults - replace with FMEA-derived values | docs/risk_weights.md | Amit |
| A14 | 20 | minutes per label per review stage (self, peer, proofreader, stakeholder); total per label depends on stages | interviewee estimate, n=1 | docs/interviews/01.md | Amit |
| A15 | TODO | label variants touched by a typical change | interviewee estimate | docs/interviews/ | Amit |
| A16 | 90-120 | change cycle time (days): about 3 months and 3-4 months | interviewee estimates, n=2 | docs/interviews/01.md, 02.md | Amit |
| A17 | TODO | cost of a labeling recall / rework | published source (verify) | | Amit |
