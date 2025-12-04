# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional: for common formats handled by markitdown extras)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy package
COPY pyproject.toml README.md ./
COPY src ./src

# Install package
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8080

# The API key must be provided at runtime: -e MARKITDOWN_WEB_API_KEY=... or config file mount
CMD ["markitdown-web", "--host", "0.0.0.0", "--port", "8080"]
