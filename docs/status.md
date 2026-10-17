# Build status against the guide's "Done when" tests

Legend: [x] done and tested · [~] partly done · [ ] team task

## Phase 0 - scope
- [ ] `docs/scope.md`: rounds, formats, dates, judging criteria, must-address checklist (needs the official brief)
- [x] Hero scenarios fixed
- [x] 2 interviews done in writing (`docs/interviews/01.md`, `02.md`); more calls with voice follow-up still wanted

## Phase 1 - repo
- [x] Folder structure, Makefile + `run.py`, `.env.example`, docker-compose, CI workflow, pre-commit, .gitignore
- [ ] Fresh clone passes `make setup && make test` on a second machine (do this on your laptop)

## Phase 2 - regulatory spine
- [x] 36 requirement rows with section + URL; every rule id exists; symbols (17 incl. 2 superseded) and glossary (30) load
- [ ] Read every clause against the source, fill `retrieved_on`, `verified_by`; second person spot-checks 20%
- [ ] Save the source PDFs in `data/regulatory/sources/` with retrieval dates
- [ ] JP/CN rows (5 each) only where verifiable

## Phase 3 - master data
- [x] `make data` builds all master files; every GTIN validates (restricted-circulation prefix 02 - verify)
- [x] Test proves every attribute key used by a template exists
- [ ] AccessGUDID extract in `data/raw/gudid/gudid_extract.csv` (bench runs the real-data check-digit test when present)

## Phase 4 - generator, defects, truth
- [x] One command rebuilds clean (72), approved base (18), defective (126 = 14 types x 9), revision pairs (10 + 3 noise),
      translation set (44) and truth files from seed 42; truth validates against a schema; byte-identical JSON/PDF
- [ ] Check a sample of 10 labels by eye
- [ ] Japanese/Chinese (Noto CJK) and Arabic panels (phase-in; markets JP/CN exist as inactive)

## Phase 5 - DB + graphs
- [x] `make db` loads with zero integrity errors; forward on CS-100 shelf life returns every expiry label;
      US pouch and EU carton get different requirement sets; synthetic history seeded and labelled

## Phase 6 - impact, drafts, intake
- [x] Scenario A: 18 impacted labels, regenerated drafts pass; Scenario B: the 6 EU pouch/carton labels fail; tests
- [ ] Record the 2-minute slice video

## Phase 7 - extraction + compliance
- [x] Every defect type D01-D14 has a detector; results table in `eval/results/`; Scenario A drafts pass;
      Scenario B labels fail with the new rule cited; report PDF with numbered evidence boxes

## Phase 8 - diff
- [x] >= 95% of seeded edits detected and classified; noise-only pairs report zero changes; planted unrequested edit
      is flagged red and blocks approval in the Scenario A demo

## Phase 9 - governance
- [x] DRAFT -> RELEASED with gates enforced in code; approve with open critical refused; forward/backward trace;
      tamper test; release ZIP with SHA-256 manifest

## Phase 10 - risk
- [x] Scenario A scores High with a visible factor breakdown; sensitivity table saved
- [ ] Replace weights with FMEA-derived values (`docs/risk_weights.md`)

## Phase 11 - AI depth
- [x] Gateway contract, cached/off modes, grounded explanations, deterministic-first semantic check, translation validator
- [ ] Optional: LaBSE similarity (`TRANSLATION_SEMANTIC=1`), Chroma retrieval for "Why is this required?" over the
      downloaded regulation texts (needs the source PDFs), 40 hand-labelled pairs for the semantic check

## Phase 12 - API + UI
- [x] All endpoints with Pydantic models (`/docs`); 10 Streamlit pages (incl. Regulatory Watch); status colours; friendly errors; Reset demo
- [x] Regulatory change monitor merged (`engines/reg_monitor.py`, page 10 Regulatory Watch): detects changes on 5 watched sources, creates pending proposals, human approval required, hand-off to Scenario B; not yet validated live end to end
- [ ] A teammate runs both scenarios from the UI without help

## Phase 13 - evaluation
- [x] Tier 1, robustness, diff, translation, ledger, risk sensitivity -> `eval/results/`
- [ ] `git tag eval-freeze`, Tier 2 blind holdout, Tier 3 photographed labels, timing study, error analysis

## Phase 14 - case artefacts
- [~] FMEA starter (`docs/fmea.csv`), AI governance page, assumptions register
- [x] As-is map, to-be map and opportunity matrix in `docs/maps/` (as-is timings from 2 interviews)
- [~] Interviews (2 written done); still to do: value stream map with measured waits, business case

## Phase 15 - deck and demo
- [~] Demo script and Q&A sheet
- [ ] Deck (12-14 slides), backup video, two timed dry runs
