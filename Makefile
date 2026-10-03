PY ?= python3
SEED ?= 42
export PYTHONPATH := $(CURDIR)

.PHONY: setup data db test bench api app demo reset clean

setup:
	$(PY) -m pip install -r requirements.txt
	$(PY) scripts/check_system.py

data:
	$(PY) -m generator.build_all --seed $(SEED)

db:
	$(PY) -m core.db --rebuild

test:
	$(PY) -m pytest -q tests

bench:
	$(PY) -m eval.run_benchmark

api:
	$(PY) -m uvicorn api.main:app --port 8000 --reload

app:
	$(PY) -m streamlit run app/Home.py --server.port 8501

demo: data db
	@echo "Starting API on :8000 and UI on :8501 (Ctrl+C to stop)"
	$(PY) -m uvicorn api.main:app --port 8000 & API_URL=http://localhost:8000 $(PY) -m streamlit run app/Home.py --server.port 8501

reset:
	$(PY) -m core.db --rebuild

clean:
	rm -rf data/generated/* data/intellilabel.db eval/results/*
