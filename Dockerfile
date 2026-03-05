FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies for python-docx and chromadb
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.4

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies (no dev deps, no interactive prompts)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --without dev

# Copy application code
COPY src/ src/
COPY knowledge/ knowledge/
COPY docs/business_rules/ docs/business_rules/

# Create output directories
RUN mkdir -p output output/.sessions output/logs

EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
