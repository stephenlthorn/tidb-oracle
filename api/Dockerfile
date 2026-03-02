FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

COPY api/pyproject.toml /app/pyproject.toml
COPY api/app /app/app
COPY api/alembic.ini /app/alembic.ini
COPY api/alembic /app/alembic
# Google service-account credentials are optional and must be provided at runtime
# via secret/volume mount (do not bake secrets into images).
COPY data /app/data

RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
