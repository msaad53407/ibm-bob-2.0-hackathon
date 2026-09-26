# Traffic-runner — synthetic verifier, fires spec CASES at stable+canary.
# Context: ./workers  (traffic-runner Dockerfile + shared/ helpers)
# No EXPOSE: this service makes outbound probes only, it serves no port.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps first for layer caching. Keep in sync with traffic-runner/pyproject.toml [project] dependencies.
COPY traffic-runner/pyproject.toml ./
RUN pip install --no-cache-dir "httpx>=0.27" "supabase>=2.4" "pydantic-settings>=2.2"

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser traffic-runner/_paths.py traffic-runner/settings.py traffic-runner/probe.py ./
COPY --chown=appuser:appuser traffic-runner/store.py traffic-runner/runner.py ./
COPY --chown=appuser:appuser shared/log_row.py shared/verification.py ./shared/
USER appuser

CMD ["python", "runner.py"]
