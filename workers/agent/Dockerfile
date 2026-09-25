FROM python:3.12-slim
WORKDIR /app
COPY agent/pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn supabase httpx langgraph pydantic-settings
COPY agent/graph.py ./
COPY shared/log_row.py shared/verification.py ./shared/
EXPOSE 8003
CMD ["uvicorn", "graph:app", "--host", "0.0.0.0", "--port", "8003"]
