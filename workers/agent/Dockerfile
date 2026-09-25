FROM python:3.12-slim
WORKDIR /app
COPY agent/pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn supabase httpx langgraph
COPY agent/graph.py ./
COPY shared/log_row.py ./shared/log_row.py
EXPOSE 8003
CMD ["uvicorn", "graph:app", "--host", "0.0.0.0", "--port", "8003"]
