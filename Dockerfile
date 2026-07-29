# DOCKERFILE FOR BUILDING FASTAPI IMAGE
# BUILD USING `docker build -f Dockerfile . -t einkaufsliste-api:latest`

## BUILD STAGE
FROM ghcr.io/astral-sh/uv:python3.11-alpine AS builder

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy configuration files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv sync (cached layer)
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application code
COPY . .

# Sync the project itself (installs application entrypoints)
RUN uv sync --frozen --no-dev

## RUNTIME STAGE
FROM python:3.11-alpine

WORKDIR /app

# Non-root user (uid/gid 1000 matches the Helm chart's podSecurityContext,
# so ownership lines up whether run via docker-compose or Kubernetes).
RUN addgroup -g 1000 -S appuser && adduser -u 1000 -S -G appuser appuser \
    && mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
# Copy application files
COPY --chown=appuser:appuser . .

USER appuser

# Expose the API port
EXPOSE 8080

# Run using the python interpreter in the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "main.py"]
