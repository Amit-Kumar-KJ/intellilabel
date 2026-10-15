# Scope sheet (Phase 0)

Last updated: 2026-10-15 | Owner: Amit | Basis: the official case brief (Case Study 4)

Every later decision is checked against this page. The brief does not state everything we need. Anything it
leaves out is marked **To confirm** and must not be quoted as fact in the deck or the demo.

## 1. Case summary

| Item | Detail |
|---|---|
| Case | Case Study 4: End-to-End Labeling Automation Management for Medical Devices (Tata Elxsi case competition) |
| Theme | Intelligent Medical Device Labeling Automation Platform |
| Challenge | Redesign the end-to-end labeling lifecycle with AI, ML, generative AI, RPA, computer vision, smart workflows and cloud technologies, to speed up regulatory compliance, reduce human effort and cycle time, minimize errors and improve patient safety |
| Expected output | "New approach using AI with artifacts or supported data" (brief) |
| Regulators named | EU MDR, US FDA, global submissions |
| Our solution | IntelliLabel AI, a working prototype: change intake, impact analysis, draft regeneration, diff and compliance checking, risk-routed e-signature, release package, audit and trace |

## 2. Competition rounds

The brief does not state rounds, dates, submission formats or limits. These must be confirmed with the organisers.

| Round | Date | What is submitted | Format / limits | Code or demo link required? |
|---|---|---|---|---|
| 1 | To confirm | To confirm | To confirm | To confirm |
| 2 | To confirm | To confirm | To confirm | To confirm |
| Final | To confirm | To confirm | To confirm | To confirm |

If Round 1 is a deck or report only: submit a deck built from the regulatory spine (Phases 2-3), the process
artefacts (Phase 14) and the slice video (Phase 6); the prototype then becomes preparation for the next round.

## 3. Judging criteria (copied from the brief)

- Understanding of labeling problem
- Regulatory/compliance awareness
- Innovation ideas considering Label Design using AI
- AI/automation platform
- End-to-end process coverage
- Accuracy & validation approach
- Traceability & auditability

Weights and scoring scale: not stated in the brief. To confirm.

## 4. "Must explicitly address" checklist (from the brief)

Status key: Covered = built and tested in the prototype; Partly = built in part or not yet measured; Gap = not done.

| # | Pain point named in the brief | Our answer | Where | Status |
|---|---|---|---|---|
| 1 | Time-consuming manual process | Impact analysis, drafting and checking run automatically; people confirm and sign | `engines/impact.py`, `engines/compliance.py` | Partly: time saving not yet measured (timing study pending) |
| 2 | Frequent regulatory updates | New requirement entered as a regulatory change request; generic rule R20 enforces it without new code (Scenario B) | `data/regulatory/requirements.csv`, `engines/rules/presence.py` | Partly: automatic source monitoring is an open pull request, not merged |
| 3 | Symbol management | Versioned symbol library, current-version check, size and overlap check, market-specific templates | `data/regulatory/symbols.csv`, rules R15, R16 | Covered (prototype uses simplified symbols, not the licensed ISO 15223-1 set) |
| 4 | Multiple sources of truth | One master data set feeds every label | `data/master/`, `core/master.py` | Partly: no live PLM or ERP connection |
| 5 | Expertise dependency | Expert checks written as 21 rules; each finding gives clause, evidence box and explanation | `engines/rules/`, `engines/compliance.py` | Covered |
| 6 | Manual redlining | Content-level and pixel-level artwork diff with overlay; unexplained changes block approval | `engines/diff.py` | Covered |
| 7 | Repetitive review | Rules R01 to R21 repeat the standard checks on every label | `engines/rules/` | Covered |
| 8 | Traceability | Forward and backward trace, hash-chained audit ledger, signatures bound to the label file hash, release manifest | `core/audit.py`, `core/workflow.py`, `core/services.py` | Covered |
| 9 | Variant explosion | Variant matrix and dependency graph: 18 active variants, 36 with planned Japan and China | `core/graph.py`, `eval/results/variant_matrix.json` | Covered at prototype scale; not tested at thousands of variants |
| 10 | Human error | Labels regenerated from approved data; UDI generated and checked; unexplained edits blocked | `generator/`, rules R01 to R04 | Covered |

## 5. Recommended method in the brief, and our status

| Step in the brief | Our status |
|---|---|
| Discover: identify manual activities, bottlenecks and error-prone tasks; create a process map | Not done. Needs interviews. |
| Analyse: root cause, failure mode analysis, value stream map; automation opportunity matrix | FMEA starter exists (`docs/fmea.csv`). Value stream map and opportunity matrix not done. |
| Innovate: identify applicable technologies (AI, GenAI, ML, computer vision, RPA, cloud) | Technology choices recorded in `docs/decisions.md` and `docs/ai_governance.md`. |
| Design and develop labels using AI | Done in the prototype: labels regenerated from approved master data. |
| Design system architecture and automation workflow | Done: pipeline, API and UI in the README. Workflow gates are enforced in code. |
| Measure time reduction, error reduction, compliance improvement, cost savings | Error detection and compliance measured on synthetic data (`eval/results/`). Time and cost not yet measured. |

## 6. Scope boundaries

**In scope**
- Lifecycle from change intake to release, audit and trace, for one hero device family
- US and EU in depth; pouch, carton and shipper packaging levels; English, German and French
- Two scenarios: a product change (A) and a regulatory change (B)
- Measured accuracy on synthetic labels, with limitations stated

**Out of scope for now**
- Active Japan and China markets, and Japanese, Chinese and Arabic panels (modelled as planned, inactive)
- Saudi Arabia and the wider Middle East, although the brief mentions them
- Live integration with PLM, ERP or artwork tools
- Augmented reality verification and a fully agentic multi-agent ecosystem (future vision)
- A validated, production-grade 21 CFR Part 11 implementation and real identity management
- Any real company's labels or identifiers; all data is synthetic

## 7. Hero device and scenarios (fixed)

- **Device family:** CardioSafe coronary stents, 3 SKUs: CS-100 (2.5 mm), CS-200 (3.0 mm), CS-300 (3.5 mm), all 18 mm.
  Class III, sterile (ethylene oxide), single use, MR Conditional, implantable. Manufacturer is fictional
  (Meridian Vascular Inc., US) so it is outside the EU, which exercises EC REP and importer rules.
- **Markets:** US and EU in depth; JP and CN modelled as planned (inactive) markets; Saudi Arabia out of scope.
- **Packaging levels:** sterile pouch (primary), unit carton (secondary), shipper (tertiary).
- **Scenario A (product change):** shelf life 24 -> 36 months and sterilization wording MT-STER-01 -> MT-STER-02.
- **Scenario B (regulatory change):** new EU requirement REQ-EU-030 (indication that the device is a medical
  device, MDR Annex I 23.2(q) - verify); all 6 EU pouch/carton labels fail it.

## 8. Stakeholders in the brief, and how the prototype represents them

| Stakeholder | Role in the brief | In IntelliLabel |
|---|---|---|
| Regulatory Affairs | Compliance management and change impact assessment | Signing roles `regulatory_affairs` and `regulatory_affairs_2`; Regulatory tab in Change Intake; Impact page |
| Product Owner(s) | Own product changes | Raise a change request in Change Intake |
| Labeling Engineers | Create and maintain labels | Signing role `labeling_engineer`; Drafts and Redline page |
| Quality Assurance | Verification and validation | Signing role `quality_assurance`; Compliance Report page |
| Manufacturing | Print readiness and production release | Receives the release package (approved PDF and SHA-256 manifest) |
| Supply Chain | Product traceability | Forward trace of identifiers to labels (Trace and Audit page) |
| Clinical Teams | Safety and usage information | Signing role `clinical_safety` for high-risk changes |
| IT and Digital Transformation | Platform implementation | FastAPI service and Streamlit UI; PLM and ERP connectors are future work |

## 9. Interviews

No interviews are recorded yet. Update this table as calls are booked. Question list: `docs/interview_script.md`.

| # | Who (role, org type) | Booked for | Done | Notes file |
|---|---|---|---|---|
| 1 | Regulatory affairs, labeling or QA professional at a device manufacturer (target) | To book | [ ] | docs/interviews/01.md |
| 2 | Regulatory or quality consultant, or a labeling or artwork specialist (target) | To book | [ ] | docs/interviews/02.md |
| 3 | Hospital biomedical engineer, or NIT Raipur alumnus in the industry (target) | To book | [ ] | docs/interviews/03.md |

## 10. Open questions for the organisers

- [ ] Round dates, what is submitted in each round, and the format and length limits
- [ ] Whether a working demo or code link is required, and whether a prototype on synthetic data is acceptable
- [ ] Scoring weights for the seven criteria
- [ ] Team size and eligibility rules, and the presentation length and Q&A format
- [ ] Whether mentors or industry contacts are available for interviews

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-10-15 | Completed from the official brief: summary, criteria, must-address checklist, method status, boundaries, stakeholders, open questions | Amit |
