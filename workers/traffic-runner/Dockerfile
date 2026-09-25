FROM python:3.12-slim
WORKDIR /app
COPY traffic-runner/pyproject.toml ./
RUN pip install --no-cache-dir httpx supabase pydantic-settings
COPY traffic-runner/runner.py ./
COPY shared/log_row.py shared/verification.py ./shared/
CMD ["python", "runner.py"]
