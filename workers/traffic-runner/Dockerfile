FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir httpx supabase
COPY runner.py ./
CMD ["python", "runner.py"]
