FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dedykowany użytkownik zapobiega tworzeniu plików Parquet i bazy SQLite z prawami roota na hoście.
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install . && \
    mkdir -p /app/data/raw /app/data/processed && \
    chown -R appuser:appgroup /app

USER appuser

ENTRYPOINT ["steam-pipeline"]
CMD ["run-all"]