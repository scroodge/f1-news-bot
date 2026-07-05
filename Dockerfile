FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# System dependencies (psycopg2, lxml builds; curl for healthcheck)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

RUN mkdir -p logs

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (overridden in docker-compose)
CMD ["python", "start_local.py"]
