# Isolated local development

Use this workflow for routine UI and API preview work. It uses a persistent local
database, synthetic acceptance records, and loopback ports **13080** (frontend),
**18080** (API), and **55432** (optional PostgreSQL). It never reads the primary
checkout's private `.env` files. The launcher refuses remote database/API values
inherited from your shell and refuses private environment files in this checkout.
The existing services on ports 3000 and 8000 can keep running.

## Start with the existing acceptance database (works without Docker)

From a clean, isolated checkout, install dependencies once:

```sh
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Then run in two terminals from the checkout root:

```sh
venv/bin/python scripts/local_dev.py api
venv/bin/python scripts/local_dev.py frontend
```

Open `http://127.0.0.1:13080`. The real FastAPI app runs on the existing browser
acceptance fixture, persisted at `.local-dev/acceptance.sqlite`. Subsequent starts
reuse it only when every seeded row still matches the synthetic fixture. Older
fixture databases must be recreated in this isolated checkout because the
fixture now uses a fixed synthetic timestamp. This SQLite path is suitable for UI work and the representative routes
below; PostgreSQL-specific routes should use the PostgreSQL path. The fixture is
deliberately limited: two counties, two fiscal periods, one published synthetic
audit finding and one withheld uncited finding. Source titles and finding text say
**Synthetic**. Fixture links use `example.invalid` and do not represent real
publications. Missing figures remain absent: Mombasa has no budget, and the
national fiscal summary returns `no_data` with `current: null`.

## Use persistent PostgreSQL when Docker is available

`docker-compose.local.yml` starts only a local PostgreSQL 17 database, bound to
127.0.0.1:55432. It has a dedicated named volume and a fixed local-only database
name. It starts no ETL worker, proxy, cache, or application container.

```sh
venv/bin/python scripts/local_dev.py db-up
venv/bin/python scripts/local_dev.py api --db postgres
venv/bin/python scripts/local_dev.py frontend
```

The API bootstraps the same acceptance records and refuses any database already
containing other data. It checks existing tables and the full seeded row values
before any schema write; changed or extra rows require a fresh dedicated fixture
database. The browser acceptance control may change the latest Nairobi budget
between KES 100 billion and KES 125 billion. PostgreSQL query sessions use
`application_name=auditgava-local-dev-api`. The API disables background jobs and
blocks external requests made through requests/httpx. Use `docker compose -f docker-compose.local.yml -p auditgava-local-dev
stop postgres` to stop only this database container; the volume persists.

Do not copy a production `.env` into this checkout. The launcher supplies local
API and dummy local Supabase auth values to Next.js. Authentication and upstream
publisher flows are outside this fixture. It does not regenerate source-backed
production datasets or import a production database snapshot.
The enhanced county API base is pinned to an unavailable loopback fixture path;
an inherited remote value stops startup.

## Verify the fixture before preview work

```sh
venv/bin/python scripts/local_dev.py check
venv/bin/python scripts/local_dev_smoke.py
```

Nairobi's synthetic budget is KES 100 billion by default and KES 50 billion
for FY2024/25. The audit list exposes one synthetic warning; the later uncited
row stays withheld. The fiscal summary remains `no_data`. Restart the API to
confirm the database persists. Change the frontend preview's URL to 13080 and
run future browser checks there. Avoid launching the old preview command that
loads the primary checkout's backend environment against Supabase.

## Deliberate production diagnostics

Production diagnostics use a **separate command and credential**, never this
launcher. Obtain a database role with SELECT-only grants, provide its connection
URL for a single command, and run:

```sh
PRODUCTION_DIAGNOSTIC_DATABASE_URL='postgresql://READ_ONLY_ROLE:...@HOST:PORT/DB?sslmode=require' \
  venv/bin/python scripts/production_diagnostic.py
```

That script starts a read-only transaction, checks the server's
`transaction_read_only` state, sets an eight-second statement timeout, and reads
only aggregate client counts from `pg_stat_activity`. The database role's grants
are the durable protection; `application_name` is only an identification label.
Remote URLs must explicitly request `sslmode=require`, `verify-ca`, or
`verify-full`. Only a loopback TCP URL may omit TLS, for the local container.
Do not put the diagnostic URL in a repository env file or use it with
`scripts/local_dev.py`.
