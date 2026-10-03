"""Central configuration: paths and environment settings."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ASSETS = ROOT / "assets"
SYMBOL_DIR = ASSETS / "symbols"
TEMPLATE_DIR = ASSETS / "templates"
DATA = ROOT / "data"
REG_DIR = DATA / "regulatory"
MASTER_DIR = DATA / "master"
GEN_DIR = DATA / "generated"
LABEL_DIR = GEN_DIR / "labels"
DEFECT_DIR = GEN_DIR / "defective"
PAIRS_DIR = GEN_DIR / "pairs"
DRAFT_DIR = GEN_DIR / "drafts"
RELEASE_DIR = DATA / "releases"
REPORT_DIR = GEN_DIR / "reports"
EVAL_DIR = ROOT / "eval" / "results"
PROMPT_DIR = ROOT / "engines" / "prompts"
LLM_CACHE = DATA / "llm_cache.json"

SEED = int(os.getenv("SEED", "42"))
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA / 'intellilabel.db').as_posix()}"
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////"):
    rel = DATABASE_URL[len("sqlite:///"):]
    if not Path(rel).is_absolute():
        DATABASE_URL = f"sqlite:///{(ROOT / rel).as_posix()}"

LLM_MODE = os.getenv("LLM_MODE", "cached").lower()  # live | cached | off
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

DPI = 300
MM_PER_PX = 25.4 / DPI

for d in (GEN_DIR, LABEL_DIR, DEFECT_DIR, PAIRS_DIR, DRAFT_DIR, RELEASE_DIR, REPORT_DIR, EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)
