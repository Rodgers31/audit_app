"""Run the real API on the explicit local PostgreSQL fixture database."""

import os
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
if (
    url.get_backend_name() != "postgresql"
    or url.host != "127.0.0.1"
    or url.port != 55432
    or url.database != "auditgava_local_dev"
    or url.query.get("application_name") != "auditgava-local-dev-api"
    or set(url.query) != {"application_name"}
):
    raise RuntimeError("Local PostgreSQL API refuses this database target")

import database
from dev_fixtures import block_external_http, seed_local_fixture

seed_local_fixture(database)
block_external_http()

import main


@asynccontextmanager
async def no_background_jobs(app):
    yield


main.app.router.lifespan_context = no_background_jobs
main.app.router.on_startup.clear()
main.app.router.on_shutdown.clear()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=18080)
