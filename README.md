# IntelliLabel AI

A working prototype for **end-to-end medical device labelling** (Tata Elxsi case competition). It takes a product
or regulatory change through impact analysis, draft regeneration, verification, risk-routed approval, release
and audit, and it measures its own accuracy.

> **Rules decide, AI proposes and explains, humans sign.**

```
change intake -> impact -> drafts -> diff + compliance -> risk-routed e-sign -> release package -> audit + trace
   (LLM parse,      (graph     (deterministic   (extraction from artwork,   (gates enforced   (ZIP + SHA-256    (hash-chained
    human confirms)  forward)   generator)       R01-R21 rules, SSIM diff)   in code)          manifest)         ledger)
```

Hero device: **CardioSafe** coronary stents (3 SKUs, Class III, sterile EO, single use, MR Conditional) from a
fictional US manufacturer, labelled for the **US and EU** at pouch, carton and shipper level, in EN/DE/FR.

## Quick start

Requirements: Python 3.11+, plus system libraries `tesseract-ocr` (+ `tesseract-ocr-deu`, `-fra`), `libzbar0`,
`libdmtx0b`. On Windows use **WSL2 (Ubuntu)**:

```bash
sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-fra libzbar0 libdmtx0b poppler-utils make
python3 -m venv .venv && source .venv/bin/activate
make setup      # pip install + system check
make data       # glyphs, GTINs, 18 approved labels, 72 clean, 126 defective, 13 diff pairs, translation set (~30 s)
make db         # SQLite tables, integrity checks, synthetic history
make test       # pytest
make bench      # all evaluations -> eval/results/ (results.md)
make app        # Streamlit UI on http://localhost:8501 (calls the API in-process)
```

No `make`? Use `python run.py setup|data|db|test|bench|api|app|demo` (same targets).
Two-process mode like production: `make api` (FastAPI docs at http://localhost:8000/docs) and
`API_URL=http://localhost:8000 make app`. Docker: `docker compose up` (Postgres + pgvector, API, app).

### LLM

Copy `.env.example` to `.env`. `LLM_MODE=cached` (default) replays stored responses, so the demo never needs
the network. `live` calls your provider (`LLM_PROVIDER=anthropic` or any OpenAI-compatible endpoint via
`LLM_BASE_URL`) and caches the answers. `off` disables every LLM feature; the app still runs end to end.
The two demo sentences ship with **hand-written fixtures** (marked as such in `data/llm_cache.json`), not model output.

Demo password for e-signatures: `intellilabel`.

## What is in the box

| Phase | Where | Status |
|---|---|---|
| 1 Repo, Makefile, CI, Docker | `Makefile`, `run.py`, `.github/workflows`, `docker-compose.yml` | done |
| 2 Regulatory spine | `data/regulatory/requirements.csv` (36 rows), `symbols.csv`, `data/master/glossary.csv` (30 terms) | done, **rows UNVERIFIED** |
| 3 Master data, GS1 | `data/master/*.csv`, `core/gs1.py`, `generator/master_build.py` | done (AccessGUDID extract: TODO) |
| 4 Generator, defects, truth | `generator/`, `assets/templates/*.yaml`, `assets/symbols/` | done |
| 5 DB + graphs | `core/models.py`, `core/db.py`, `core/graph.py` | done |
| 6 Impact, drafts, NL intake | `engines/impact.py`, `engines/llm_gateway.py` | done |
| 7 Extraction + rules + report | `engines/extraction.py`, `engines/rules/`, `engines/compliance.py` | done |
| 8 Diff engine | `engines/diff.py` | done |
| 9 Workflow, ledger, trace, release | `core/workflow.py`, `core/audit.py`, `core/services.py` | done |
| 10 Risk scoring | `core/risk.py` | done (weights to be tied to FMEA) |
| 11 AI depth | gateway contract, semantic check, translation validator | done; LaBSE similarity + RAG "Why?" optional |
| 12 API + UI | `api/main.py`, `app/` (10 pages) | done |
| 13 Evaluation | `eval/run_benchmark.py` | Tier 1 + robustness done; Tier 2/3 + timing study: team |
| 14 Case artefacts | `docs/` | starters; interviews, VSM, maps, business case: team |
| 15 Deck, demo | `docs/demo_script.md`, `docs/qa_prep.md` | script ready; deck: team |

See `docs/status.md` for the done-when checklist and what is left for the team.

## Layout

```
assets/       fonts, our own simplified symbol glyphs, label templates (YAML)
data/         regulatory spine, master data, generated labels and truth files (make data)
core/         config, gs1, models, db, graph, audit ledger, workflow, risk, services
generator/    glyphs, label generator/renderer, defect injector, translation set, build_all
engines/      extraction, rules/ (one file per family), compliance, diff, impact, translation, llm_gateway, prompts/
api/          FastAPI (all logic behind endpoints)
app/          Streamlit pages (only call the API)
eval/         benchmark script and results
docs/         scope, assumptions, decisions, FMEA, risk weights, AI governance, demo, Q&A, procedures
tests/        pytest (one pass/fail per rule, done-when tests per phase)
```

## Honesty notes
- All products, companies and labels are synthetic. Do not reuse a real company's identifiers.
- Every regulatory row is marked `UNVERIFIED` and every clause `(verify)` until checked against the source text.
- Symbols are our own simplified glyphs; production would use the licensed ISO 15223-1 library.
- Tier 1 results are an upper bound (detectors were built against these defects).
