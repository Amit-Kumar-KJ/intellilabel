"""Cross-platform task runner (same targets as the Makefile) for Windows without `make`.

    python run.py setup | data | db | test | bench | api | app | demo | reset
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}

TASKS = {
    "setup": [[PY, "-m", "pip", "install", "-r", "requirements.txt"], [PY, "scripts/check_system.py"]],
    "data": [[PY, "-m", "generator.build_all"]],
    "db": [[PY, "-m", "core.db", "--rebuild"]],
    "test": [[PY, "-m", "pytest", "-q", "tests"]],
    "bench": [[PY, "-m", "eval.run_benchmark"]],
    "api": [[PY, "-m", "uvicorn", "api.main:app", "--port", "8000"]],
    "app": [[PY, "-m", "streamlit", "run", "app/Home.py", "--server.port", "8501"]],
    "reset": [[PY, "-m", "core.db", "--rebuild"]],
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS | {"demo": None}:
        print(__doc__)
        sys.exit(1)
    task = sys.argv[1]
    if task == "demo":
        for t in ("data", "db"):
            for cmd in TASKS[t]:
                subprocess.run(cmd, cwd=ROOT, env=ENV, check=True)
        api = subprocess.Popen(TASKS["api"][0], cwd=ROOT, env=ENV)
        try:
            subprocess.run(TASKS["app"][0], cwd=ROOT, env={**ENV, "API_URL": "http://localhost:8000"})
        finally:
            api.terminate()
        return
    for cmd in TASKS[task]:
        subprocess.run(cmd, cwd=ROOT, env=ENV, check=True)


if __name__ == "__main__":
    main()
