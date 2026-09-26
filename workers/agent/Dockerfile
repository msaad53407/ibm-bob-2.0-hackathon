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
COPY --chown=appuser:appuser agent/_paths.py agent/settings.py agent/criticality.py agent/decision.py ./
COPY --chown=appuser:appuser agent/store.py agent/proxy.py agent/schemas.py agent/service.py agent/graph.py ./
COPY --chown=appuser:appuser shared/log_row.py shared/verification.py ./shared/
USER appuser

EXPOSE 8003
CMD ["uvicorn", "graph:app", "--host", "0.0.0.0", "--port", "8003"]
