# Demo API (Stable/Canary) — same image, BUG_PROFILE selects behaviour.
# Context: ./services/api-demo
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps first for layer caching. Keep in sync with pyproject.toml [project] dependencies.
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "pydantic-settings>=2.2"

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser app ./app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
