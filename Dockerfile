# LARA — Latram Shop internal support agent (HF Spaces / any container host)
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.cache PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/charts data/logs data/reports && chmod -R 777 data .cache 2>/dev/null || true

EXPOSE 7860
# Index builds lazily on first question; boot is instant for /health
CMD ["uvicorn", "src.app.api:app", "--host", "0.0.0.0", "--port", "7860"]
