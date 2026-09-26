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
COPY --chown=appuser:appuser agent/_paths.py ./
COPY --chown=appuser:appuser agent/api/__init__.py agent/api/app.py agent/api/schemas.py ./api/
COPY --chown=appuser:appuser agent/domain/__init__.py agent/domain/decision.py agent/domain/criticality.py ./domain/
COPY --chown=appuser:appuser agent/adapters/__init__.py agent/adapters/jev.py agent/adapters/store.py agent/adapters/proxy.py ./adapters/
COPY --chown=appuser:appuser agent/config/__init__.py agent/config/settings.py ./config/
COPY --chown=appuser:appuser agent/workflow/__init__.py agent/workflow/state.py agent/workflow/nodes.py agent/workflow/edges.py agent/workflow/builder.py ./workflow/
COPY --chown=appuser:appuser shared/log_row.py shared/verification.py ./shared/
USER appuser

EXPOSE 8003
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8003"]
