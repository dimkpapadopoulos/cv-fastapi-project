# 1. Pull a lightweight Python base image
FROM python:3.14-slim

# 2. Install our lightning-fast package manager, uv
RUN pip install uv

# 3. Set the working directory inside the container
WORKDIR /app

# 4. Copy ONLY our dependency files first (for caching efficiency)
COPY pyproject.toml uv.lock ./

# 5. Install the dependencies
RUN uv sync

# 6. Copy the rest of our application code (main.py, etc.)
COPY . .

# 7. Tell the container how to start the FastAPI server
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]