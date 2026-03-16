FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies (kept minimal; extend if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and source
COPY pyproject.toml README.md /app/
COPY bess_model /app/bess_model
COPY config.example.yaml /app/config.example.yaml
COPY data /app/data

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    (pip install --no-cache-dir ".[dev]" || pip install --no-cache-dir .)

# Default port and command for the web UI
ENV PORT=5000
EXPOSE 5000

CMD ["bess-model-web", "--config", "config.example.yaml", "--host", "0.0.0.0", "--port", "5000"]

