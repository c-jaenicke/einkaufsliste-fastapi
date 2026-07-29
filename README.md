# Einkaufsliste - Python FastAPI Backend

This is a complete rewrite of the original Go Gin/Ent backend in Python, using **FastAPI**, **Pydantic**, and **psycopg3** (async pool).

## Features

- **Database Table Initialization**: Runs on startup to auto-generate `categories`, `stores`, and `items` tables with the exact column structures and foreign key rules (`ON DELETE SET NULL`) of the original schema.
- **Default Database Verification**: Auto-populates the default `"keine"` category and `"keiner"` store if they are missing.
- **In-Memory Pet State**: Replicates the in-memory state and transitions of the companion pet endpoint.
- **100% JSON & API Compatibility**: Standardizes fields to match Gin's route structure and serializes an empty `edges` dictionary to remain perfectly backwards-compatible with the Svelte frontend.

---

## Getting Started

### 1. Prerequisites

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

### 2. Start PostgreSQL

Use the provided docker compose file to start the PostgreSQL database container (uses the pgvector-pg18 image, matching your configuration):

```bash
docker compose -f docker-compose-dev.yaml up -d
```

This starts the database locally and exposes it at `127.0.0.1:10000`.

### 3. Install Dependencies

Install all dependencies in a local virtual environment:

```bash
uv sync
```

### 4. Run the Backend

Start the Uvicorn ASGI server with automatic reload:

```bash
uv run python main.py
```

The API will be available at [http://localhost:8080](http://localhost:8080).

---

## Configuration

Settings are loaded via `pydantic-settings` from `.env-dev` or standard environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DSS` | Full connection string (optional) | _Constructed automatically if empty_ |
| `POSTGRES_USER` | DB Username | `einkaufsliste-dev` |
| `POSTGRES_PASSWORD` | DB Password | `einkaufsliste-dev-pass` |
| `POSTGRES_DB` | DB Name | `einkfaufsliste-dev` |
| `POSTGRES_HOST` | DB Host | `127.0.0.1` |
| `POSTGRES_PORT` | DB Port | `10000` |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | `http://localhost:3000` |
| `TZ` | App Timezone | `Europe/Berlin` |

---

## Docker Build

To package this application as a container:

```bash
docker build -f Dockerfile -t einkaufsliste-api:latest .
```
