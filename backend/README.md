# Kenya Audit Transparency — Backend

FastAPI backend powering the Kenya Audit Transparency Platform. Provides REST APIs for government financial data, audit reports, county budgets, economic indicators, and more.

## Prerequisites

| Dependency   | Version              | Notes                                                  |
| ------------ | -------------------- | ------------------------------------------------------ |
| Python       | 3.12+                | Required                                               |
| PostgreSQL   | 15+ (17 recommended) | Primary database                                       |
| Redis        | 7+                   | Optional — caching, gracefully degrades if unavailable |
| Java Runtime | 8+                   | Required by `tabula-py` for PDF table extraction       |

## Quick Start

```bash
# 1. Clone and navigate
cd audit_app/backend

# 2. Create and activate virtual environment
python3 -m venv ../venv
source ../venv/bin/activate   # <-- required before every session

# 3. Install dependencies
pip install -r requirements-dev.txt   # includes test/lint tools
# — or for production only —
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your database credentials, secrets, etc.

# 5. Set up the database
alembic upgrade head

# 6. Seed initial data
python -m seeding.cli seed --all --dry-run   # preview first
python -m seeding.cli seed --all             # apply

# 7. Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at **http://localhost:8000** with interactive docs at:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Environment Variables

Copy `.env.example` to `.env` and configure:

### Core

| Variable                      | Default                                                   | Description                              |
| ----------------------------- | --------------------------------------------------------- | ---------------------------------------- |
| `DATABASE_URL`                | `postgresql://postgres:password@localhost:5432/audit_app` | Full PostgreSQL connection string        |
| `SECRET_KEY`                  | —                                                         | JWT signing key (change in production!)  |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                                                      | JWT token expiry                         |
| `DEBUG`                       | `true`                                                    | Debug mode                               |
| `ENVIRONMENT`                 | `development`                                             | `development` / `staging` / `production` |
| `LOG_LEVEL`                   | `INFO`                                                    | Python logging level                     |

### Services

| Variable                  | Default                  | Description                          |
| ------------------------- | ------------------------ | ------------------------------------ |
| `REDIS_URL`               | `redis://localhost:6379` | Redis connection (optional)          |
| `SENTRY_ENABLED`          | `false`                  | Exact lowercase `true` enables Sentry; `false` disables it |
| `SENTRY_DSN`              | —                        | Valid nonempty DSN required when enabled; ignored when disabled |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1`                  | Finite number from 0 to 1, inclusive; used only when enabled |
| `ADMIN_API_AUTH_REQUIRED` | `false`                  | Require auth for admin endpoints     |

### AWS S3 (Document Storage)

| Variable                | Description                    |
| ----------------------- | ------------------------------ |
| `AWS_ACCESS_KEY_ID`     | AWS access key                 |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key                 |
| `AWS_BUCKET_NAME`       | S3 bucket name                 |
| `AWS_REGION`            | AWS region (e.g., `us-east-1`) |

### Email (SMTP Notifications)

| Variable        | Default          | Description  |
| --------------- | ---------------- | ------------ |
| `SMTP_HOST`     | `smtp.gmail.com` | SMTP server  |
| `SMTP_PORT`     | `587`            | SMTP port    |
| `SMTP_USER`     | —                | Sender email |
| `SMTP_PASSWORD` | —                | App password |

### Seeding Configuration

| Variable                       | Default      | Description                                         |
| ------------------------------ | ------------ | --------------------------------------------------- |
| `SEED_RATE_LIMIT`              | `60/min`     | Rate limit for external fetches                     |
| `SEED_TIMEOUT_SECONDS`         | `30.0`       | HTTP request timeout                                |
| `SEED_MAX_RETRIES`             | `3`          | Retry count for failed fetches                      |
| `SEED_DRY_RUN_DEFAULT`         | `false`      | Default dry-run mode                                |
| `SEED_BUDGET_DEFAULT_CURRENCY` | `KES`        | Currency for budget data                            |
| `SEED_*_DATASET_URL`           | `file://...` | Data source URLs (see `.env.example` for full list) |

> **Tip:** During development, seed data URLs use `file://` paths pointing to local JSON fixtures in `seeding/real_data/` and `seeding/fixtures/`. For production, replace these with live government API endpoints.

## Project Structure

```
backend/
├── main.py                  # FastAPI app entry point (routes + middleware)
├── database.py              # SQLAlchemy engine, session, get_db dependency
├── models.py                # SQLAlchemy ORM models
├── schemas.py               # Pydantic request/response schemas
├── auth.py                  # JWT authentication
├── bootstrap.py             # App startup bootstrap logic
├── conftest.py              # Shared pytest fixtures
│
├── config/
│   ├── settings.py          # Pydantic Settings (env-based configuration)
│   └── secrets.py           # Secrets backend (env / AWS / Vault)
│
├── routers/
│   ├── admin.py             # Admin management endpoints
│   ├── economic.py          # Economic indicators endpoints
│   ├── etl_admin.py         # ETL administration endpoints
│   └── health.py            # Health check endpoints
│
├── services/
│   ├── auto_seeder.py       # Automated data seeding
│   ├── question_service.py  # Learning hub Q&A service
│   ├── live_data_fetcher.py # Real-time external data fetcher
│   └── ...                  # Other service modules
│
├── middleware/
│   └── security.py          # Rate limiting, security headers
│
├── seeding/
│   ├── cli.py               # CLI entry point (python -m seeding.cli)
│   ├── config.py            # Seeding configuration
│   ├── domains/             # Domain-specific seed handlers
│   ├── fixtures/            # Static seed data (JSON)
│   ├── real_data/           # Curated real-world data (JSON)
│   ├── pdf_parsers.py       # PDF report extraction
│   ├── http_client.py       # HTTP client with retry/rate-limit
│   └── rate_limiter.py      # Rate limiter for external APIs
│
├── cache/                   # Redis cache layer
├── monitoring/
│   ├── alerts.py            # Alert definitions
│   └── instrumentation.py   # Prometheus metrics
├── validators/
│   └── data_validator.py    # Data validation rules
│
├── alembic/                 # Alembic migration environment
│   ├── env.py
│   └── versions/            # Migration scripts
├── alembic.ini              # Alembic configuration
│
├── tests/                   # Test suite (see Testing section)
├── Dockerfile               # Development Docker image
├── Dockerfile.prod          # Production Docker image
├── requirements.txt         # Production dependencies
└── requirements-dev.txt     # Dev/test dependencies
```

## Database

### Connection

The database URL is read from the `DATABASE_URL` environment variable. Alternatively, you can set individual variables:

| Variable      | Default                                      |
| ------------- | -------------------------------------------- |
| `DB_USER`     | `postgres`                                   |
| `DB_PASSWORD` | `password`                                   |
| `DB_HOST`     | `localhost`                                  |
| `DB_PORT`     | `6543` (Supabase pooler) / `5432` (standard) |
| `DB_NAME`     | `audit_app`                                  |
| `DB_SSLMODE`  | —                                            |

### Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description of change"

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Seeding

The seeding system populates the database with real Kenyan government financial data:

```bash
# Preview what will be seeded (dry run)
python -m seeding.cli seed --all --dry-run

# Seed all data domains
python -m seeding.cli seed --all

# Seed specific domains
python -m seeding.cli seed --domain population
python -m seeding.cli seed --domain budgets
python -m seeding.cli seed --domain audits
```

Data sources are configured via `SEED_*_DATASET_URL` env vars. Local JSON fixtures are included for development.

## Running the Server

### Development

> **Important:** Always activate the virtual environment first.

```bash
# Activate the venv (from backend/ directory)
source ../venv/bin/activate

# With auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# — or without activating the venv —
../venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or using the VS Code task (venv is configured automatically):
# Terminal → Run Task → "Start Backend (Dev)"
```

### Docker

```bash
# Development
docker build -t audit-backend -f Dockerfile .
docker run -p 8000:8000 --env-file .env audit-backend

# Production
docker build -t audit-backend-prod -f Dockerfile.prod .
docker run -p 8000:8000 --env-file .env audit-backend-prod
```

### Docker Compose (full stack)

From the project root:

```bash
docker-compose up -d          # Start all services (DB, Redis, backend, frontend)
docker-compose logs -f backend # Follow backend logs
```

## Testing

### Run Tests

Make sure the venv is activated (`source ../venv/bin/activate`) before running tests.

```bash
# All tests
pytest

# With coverage
pytest --cov=. --cov-report=term-missing

# Specific test file
pytest tests/test_health_endpoints.py

# Quick summary
pytest --tb=line -q
```

### Test Structure

| File                                    | Coverage                       |
| --------------------------------------- | ------------------------------ |
| `tests/test_models.py`                  | SQLAlchemy ORM models          |
| `tests/test_response_models.py`         | Pydantic response schemas      |
| `tests/test_cors_middleware.py`         | CORS configuration             |
| `tests/test_health_endpoints.py`        | Health check endpoints         |
| `tests/test_country_endpoints.py`       | National-level data endpoints  |
| `tests/test_county_endpoints.py`        | County-level data endpoints    |
| `tests/test_audit_endpoints.py`         | Audit report endpoints         |
| `tests/test_budget_debt_fiscal.py`      | Budget, debt, fiscal endpoints |
| `tests/test_entity_search_dashboard.py` | Search and dashboard endpoints |
| `tests/test_etl_admin_endpoints.py`     | ETL administration endpoints   |
| `tests/test_economic_endpoints.py`      | Economic indicator endpoints   |
| `tests/test_route_smoke.py`             | Smoke tests for all routes     |
| `tests/test_etl.py`                     | ETL pipeline logic             |
| `tests/test_pdf_parsers.py`             | PDF extraction                 |
| `tests/test_seeding_http_client.py`     | Seeding HTTP client            |
| `tests/test_validators.py`              | Data validators                |
| `tests/test_population_domain.py`       | Population seeding domain      |
| `tests/integration/`                    | Integration tests              |

### Test Configuration

Tests use an in-memory SQLite database with a JSONB→TEXT compile shim (see `conftest.py`). This avoids needing a running PostgreSQL instance for unit tests. Key fixtures:

- **`test_db`** — Fresh SQLite session per test
- **`client`** — FastAPI `TestClient` with all DB/middleware patches applied

## Code Quality

```bash
# Format code
black .

# Sort imports
isort .

# Lint
flake8

# Type check
mypy .
```

## API Endpoints Overview

The API exposes 60+ endpoints. Key groups:

| Group     | Prefix                   | Description                         |
| --------- | ------------------------ | ----------------------------------- |
| Health    | `/health`, `/api/health` | Liveness and readiness probes       |
| Counties  | `/api/counties`          | County profiles, budgets, audits    |
| Audits    | `/api/audits`            | Audit reports and findings          |
| Budgets   | `/api/budgets`           | National and county budgets         |
| Economic  | `/api/economic`          | GDP, inflation, economic indicators |
| Fiscal    | `/api/fiscal`            | Fiscal summaries and analysis       |
| Debt      | `/api/debt`              | National debt data                  |
| Dashboard | `/api/dashboard`         | Aggregated dashboard stats          |
| Search    | `/api/search`            | Full-text entity search             |
| Admin     | `/api/admin`             | Admin management                    |
| ETL Admin | `/api/etl`               | ETL job management                  |
| Learning  | `/api/learning`          | Learning hub questions              |

Full interactive documentation is available at `/docs` (Swagger UI) when the server is running.

## Secrets Management

The `config/secrets.py` module supports multiple backends:

| Backend | Config                              | Use Case                 |
| ------- | ----------------------------------- | ------------------------ |
| `env`   | Environment variables / `.env` file | Development              |
| `aws`   | AWS Secrets Manager                 | Production (AWS)         |
| `vault` | HashiCorp Vault                     | Production (self-hosted) |

Set the backend in `config/settings.py` or via environment variables.

## Monitoring

- **Prometheus metrics** — Exposed via `prometheus-fastapi-instrumentator` at `/metrics`
- **Sentry** — Opt in with `SENTRY_ENABLED=true` and a valid `SENTRY_DSN`.
  Missing `SENTRY_ENABLED` or exact lowercase `false` keeps monitoring dormant,
  ignoring the DSN and its secret lookup. Only exact lowercase `true` and
  `false` are accepted; other values (including empty, `TRUE`, and `1`) stop
  app construction with `Sentry startup configuration is invalid.` Enabled
  monitoring also stops startup for missing/invalid DSNs, nonfinite or
  out-of-range sampling, or SDK initialization failure. No configuration values
  or underlying exception text appear in that message. Traces default to 0.1
  only after opt-in; profiles stay disabled. Deployed capture/privacy acceptance
  remains tracked in #525.
- **Structured logging** — JSON logs via `python-json-logger` (output to `main_backend.log`)

## Troubleshooting

### Common Issues

**`psycopg2` install fails on macOS:**

```bash
brew install postgresql
pip install psycopg2-binary
```

**`tabula-py` requires Java:**

```bash
brew install openjdk       # macOS
sudo apt install default-jre  # Ubuntu/Debian
```

**Redis not available (warning, not fatal):**
The app works without Redis — caching is disabled and a warning is logged. To suppress: don't set `REDIS_URL` in `.env`.

**Database connection refused:**
Ensure PostgreSQL is running and the `DATABASE_URL` in `.env` is correct. For Docker Compose users, the database starts automatically.
