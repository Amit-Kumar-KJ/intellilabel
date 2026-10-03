# Decisions log

One line per decision: date - decision - reason.

- 2026-10-04 - SQLite by default; DATABASE_URL switches to Postgres (docker-compose has pgvector) - zero setup for demos.
- 2026-10-04 - Data Matrix is drawn with reportlab's built-in ECC200 encoder instead of treepoem - no Ghostscript
  dependency. Limitation: the symbol is not flagged as GS1 (no leading FNC1). The element string puts the only
  variable field (lot) last so no separator is needed. Production must encode GS1 mode (treepoem/bwip-js or the
  printer's driver).
- 2026-10-04 - langdetect replaced by a stopword/script heuristic in `engines/extraction.py` - langdetect failed to
  build on Python 3.13; the heuristic is deterministic and adequate for EN/DE/FR (+ script detection for JA/ZH/AR).
- 2026-10-04 - For digital PDFs, symbols are found from the embedded image boxes and classified against the glyph
  library (normalised cross-correlation); for photos/rasters, full multi-scale template matching (0.5-1.5) with NMS.
  Both read only the artwork, never label.json.
- 2026-10-04 - New regulatory requirements use the generic presence rule R20 driven by the requirement row's
  `label_element`, so Scenario B needs no new code. R21 (glossary) added beyond the R01-R19 catalogue for defect D13.
- 2026-10-04 - A regulatory requirement becomes active on confirmation of its change request (the law applies
  regardless of our release); product attribute versions stay `pending` until the change request is released.
- 2026-10-04 - Templates carry `include_if: requirement=REQ-EU-030` for the MD symbol, so regenerated Scenario B drafts
  include it and pass: closed loop.
- 2026-10-04 - Approval routing uses the risk tier of the change request; signatures bind to the SHA-256 of the
  label PDF, and a changed artefact invalidates the signature.
- 2026-10-04 - Translation completeness uses an exact sentence count (missing sentence = FAIL) because label texts are
  short; the guide's "within one" tolerance would miss a dropped sentence in a two-sentence text.
- 2026-10-04 - LLM: provider-agnostic gateway (Anthropic or any OpenAI-compatible endpoint). Default LLM_MODE=cached
  with hand-written fixtures for the two demo sentences, plus a clearly labelled rule-based fallback parser.
- 2026-10-04 - Streamlit calls the API in-process (FastAPI TestClient) when API_URL is empty, so `make app` alone runs
  the demo; with API_URL set it calls the HTTP API.
