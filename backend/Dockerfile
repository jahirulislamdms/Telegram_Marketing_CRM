FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for building psycopg / cryptography and for healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (project is installed editable so the bind-mount
# in docker-compose keeps code live-reloadable in development).
COPY pyproject.toml ./
COPY app ./app
COPY engine ./engine
COPY worker ./worker
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
