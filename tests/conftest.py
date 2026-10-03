import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# tests use their own database so they never clobber the demo DB
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'test_intellilabel.db').as_posix()}"
os.environ.setdefault("LLM_MODE", "cached")

import pytest  # noqa: E402

GEN = ROOT / "data" / "generated"
needs_data = pytest.mark.skipif(not (GEN / "ground_truth.json").exists(), reason="run `make data` first")


@pytest.fixture(scope="session")
def fresh_db():
    from core.db import rebuild

    res = rebuild(verbose=False)
    assert res["integrity_errors"] == []
    return res
