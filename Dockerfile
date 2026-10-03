FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libzbar0 libdmtx0b poppler-utils make && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg[binary]
COPY . .
ENV PYTHONPATH=/app
RUN python -m generator.build_all --seed 42 && python -m core.db --rebuild
