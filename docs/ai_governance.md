# AI governance (Phase 14.8)

**Principle: rules decide, AI proposes and explains, humans sign.**

## What the AI may do
- Parse a plain-English change into a structured change request, which a human must confirm before anything runs.
- Explain a finding in two sentences and suggest a fix, quoting the requirement text it relies on.
- Classify whether a reworded warning keeps the same meaning (`equivalent` / `different` / `unsure`); deterministic
  checks for numbers, units and negations run first.
- (Optional) draft a genuinely new sentence as a *proposed master text* that a human must approve.

## What the AI may never do
- Decide pass or fail, change a finding's status, approve, sign, waive or release.
- Invent requirements: requirement rows carry a source URL and section and are curated by people.
- Put free text on a label: labels only reference approved master texts.

## How it is grounded and logged
- Every call goes through `engines/llm_gateway.py`: registered, versioned, hashed prompts (`engines/prompts/`),
  temperature 0, JSON validated against a schema, one retry then fallback.
- Inputs come only from the database or the requirement row; any quote in an output must exist verbatim in the
  source, otherwise the output is discarded and the template message is shown.
- The audit ledger stores model, prompt hash, input hash, output hash and latency for each call.

## How it is validated
- Frozen test sets (`data/generated/*truth*`), re-run with `make bench` on every model or prompt change.
- Detectors are frozen with `git tag eval-freeze` before blind (Tier 2) and realism (Tier 3) runs.
- Overrides (waivers, accepted unexplained changes) are e-signed with a written justification and logged.

## Fallback when the AI is off
`LLM_MODE=off`: the intake page shows a structured form, explanations use the template text, the semantic check
routes to a human. The full demo runs end to end with the LLM switched off.

## Prototype limits (say so in the deck)
Simulated users and a demo password stand in for identity management. The e-signature records illustrate
21 CFR Part 11 concepts (signature meaning, linkage to the record, audit trail); a real deployment needs identity
management and formal computer-system validation (GAMP 5 / computer software assurance - verify current names).
