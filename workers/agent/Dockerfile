# Guardrail agent (FastAPI) — Decision + Proposals + gated Execution.
# Context: ./workers  (agent Dockerfile + shared/ helpers)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps first for layer caching. Keep in sync with agent/pyproject.toml [project] dependencies.
COPY agent/pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "supabase>=2.4" "httpx>=0.27" "langgraph>=0.1" "pydantic-settings>=2.2"

RUN useradd --create-home --uid 10001 appuser
# Copy whole package directories, not per-file lists: a new module that the
# Dockerfile doesn't name is a boot-time ModuleNotFoundError, and tests/ must
# stay out of the image. .dockerignore already drops __pycache__ and .env*.
COPY --chown=appuser:appuser agent/_paths.py ./
COPY --chown=appuser:appuser agent/api/ ./api/
COPY --chown=appuser:appuser agent/domain/ ./domain/
COPY --chown=appuser:appuser agent/adapters/ ./adapters/
COPY --chown=appuser:appuser agent/config/ ./config/
COPY --chown=appuser:appuser agent/workflow/ ./workflow/
COPY --chown=appuser:appuser shared/log_row.py shared/verification.py ./shared/
USER appuser

EXPOSE 8003
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8003"]
