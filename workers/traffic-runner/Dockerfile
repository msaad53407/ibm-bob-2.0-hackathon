FROM python:3.12-slim
WORKDIR /app
COPY traffic-runner/pyproject.toml ./
RUN pip install --no-cache-dir httpx supabase
COPY traffic-runner/runner.py ./
COPY shared/log_row.py ./shared/log_row.py
CMD ["python", "runner.py"]
