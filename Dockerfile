# The Scout API (the page is hosted separately on Vercel).
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scout ./scout
COPY sql ./sql
CMD exec uvicorn scout.app:app --host 0.0.0.0 --port ${PORT:-8080}
