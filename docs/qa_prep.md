# Q&A preparation (Phase 15.4)

| Question | One-line answer | Evidence |
|---|---|---|
| What happens when the LLM is wrong? | It never decides; quotes are verified against the requirement row; a human confirms every parsed change; the app runs with the LLM off. | docs/ai_governance.md, engines/llm_gateway.py |
| How do you keep regulations current? | Versioned requirement rows with source URL, section and verifier; a new row is a regulatory change request (Scenario B) that regulatory affairs confirms. | data/regulatory/requirements.csv |
| How would this be validated under Part 11 and GAMP 5? | Signatures bind meaning + user + time + artefact hash; hash-chained audit trail; formal CSV/CSA validation needed for production (verify current guidance names). | core/workflow.py, core/audit.py |
| What if a symbol is detected with low confidence? | It is marked uncertain and routed to review, never auto-passed. | engines/extraction.py, R15 |
| Why not buy an existing labeling tool? | We layer on top of PLM/ERP/artwork tools as a verification and intelligence layer. | business case slide (TODO: vendor research) |
| How good is it really? | Tier 1 numbers are an upper bound; quote Tier 2 (blind) and Tier 3 (photos) plus limitations. | eval/results/results.md |
| What does a pilot cost and how long? | TODO after interviews: one product family, shadow mode, success criteria = defects caught + review time. | docs/assumptions.md |
| Why a weighted risk score and not ML? | No real change history to train on; FMEA-based weights; sensitivity check shows ranking stability. | docs/risk_weights.md, eval/results/risk_sensitivity.json |
