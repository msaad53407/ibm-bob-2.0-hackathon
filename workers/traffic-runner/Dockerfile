# Traffic-runner — synthetic verifier, fires spec CASES at stable+canary.
# Context: ./workers  (traffic-runner Dockerfile + shared/ helpers)
# Serves POST /run (dashboard trigger) + GET /health on :8004.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps first for layer caching. Keep in sync with traffic-runner/pyproject.toml [project] dependencies.
COPY traffic-runner/pyproject.toml ./
RUN pip install --no-cache-dir "httpx>=0.27" "supabase>=2.4" "pydantic-settings>=2.2" "fastapi>=0.110" "uvicorn>=0.29" "pyyaml>=6.0"

RUN useradd --create-home --uid 10001 appuser
# Whole package directories, not per-file lists — see agent/Dockerfile.
COPY --chown=appuser:appuser traffic-runner/_paths.py ./
COPY --chown=appuser:appuser traffic-runner/api/ ./api/
COPY --chown=appuser:appuser traffic-runner/domain/ ./domain/
COPY --chown=appuser:appuser traffic-runner/adapters/ ./adapters/
COPY --chown=appuser:appuser traffic-runner/config/ ./config/
COPY --chown=appuser:appuser shared/log_row.py shared/verification.py ./shared/
USER appuser

EXPOSE 8004
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8004"]
