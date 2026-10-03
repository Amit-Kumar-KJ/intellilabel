# Demo script (about 7 minutes)

Before every run: sidebar -> **Reset demo**. Keep `LLM_MODE=cached` (have `off` ready). Record a 3-minute backup video.

| Minute | Page | What you do | What the judge should conclude |
|---|---|---|---|
| 0-1 | Dashboard | Variant count, one interview quote | This team talked to practitioners |
| 1-2 | Change Intake | Type "Extend CardioSafe shelf life to 36 months and update the sterilization wording", Parse, check the table, Confirm | AI helps, a human confirms |
| 2-3 | Impact | 18 labels, counts by market/level/language, risk bars (High, factor breakdown), approvers. Tick "simulate an artwork slip", Generate drafts | Scoping and drafting are fast and traceable |
| 3-4 | Drafts and Redline | Run verification. Open the EU carton: overlay with the IFU symbol move in thick red, "UNEXPLAINED". Show an explained change (expiry bound to shelf_life_months). Compliance page: a finding with clause citation, evidence box and Why? | Verification is concrete and explainable |
| 4-5 | Change Intake -> Regulatory tab | Create REQ-EU-030 (MD symbol). Impact lists the 6 EU pouch/carton labels with the finding | Regulatory change is covered end to end |
| 5-6 | Approval Queue | Try to move the flagged label to IN_REVIEW -> refused. Accept the change with a note. Bulk sign as each role (password `intellilabel`), approve, switch to QA, release, download the package. Trace and Audit: backward trace of expiry_date; Verify ledger; Tamper demo; Verify again -> broken row | Governed and auditable |
| 6-7 | Results | Tier 1 table, clean FP rate, diff and translation results, robustness, limitations | Accuracy is evidenced, not claimed |

Talking line for the architecture: *rules decide, AI proposes and explains, humans sign.*
