FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TESSERACT_CMD=/usr/bin/tesseract

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY frontend/ frontend/

WORKDIR /app/backend
EXPOSE 7860
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}
