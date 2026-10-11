"""Run the real legacy loader's owned write path in its own OS process (#602).

``DatabaseLoader.ensure_country_exists`` is an ``owned_write`` call: the real
``etl.writer_ownership`` acquires every LEGACY_DOMAINS claim before the loader
runs. An inert before-commit barrier, keyed to this fixture's own country code,
lets the parent observe the held claims before any effect commits. Only the
owned loopback database is reachable.
"""
import asyncio
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urlsplit

target = urlsplit(os.environ["DATABASE_URL"])
if target.hostname != "127.0.0.1" or not target.path.startswith("/batch11_602_") or target.port in (55530, 55532, 55534):
    raise SystemExit("Unowned legacy fixture database refused")
_connect = socket.socket.connect


def _owned_only(sock, address):
    if not isinstance(address, tuple) or address[:2] != (target.hostname, target.port):
        raise RuntimeError("Unowned transport refused")
    return _connect(sock, address)


socket.socket.connect = _owned_only

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
# The backend ``seeding`` package must win over the root stub, while ``etl``
# must be the root legacy package: import backend modules first, then prefer root.
sys.path[:0] = [str(BACKEND)]
import seeding.exclusion  # noqa: E402,F401
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from models import Country  # noqa: E402

sys.path.insert(0, str(ROOT))
from etl.database_loader import DatabaseLoader  # noqa: E402

CODE = "ZZB"  # inert country code owned by this fixture
control = create_engine(os.environ["DATABASE_URL"])


def mode():
    with control.connect() as c:
        return c.scalar(text("SELECT mode FROM batch11_legacy_control"))


@event.listens_for(Session, "before_commit")
def barrier(session):
    if not any(isinstance(row, Country) and row.iso_code == CODE for row in session.new):
        return
    with control.begin() as c:
        c.execute(text("INSERT INTO batch11_markers(stage) VALUES ('legacy_entered')"))
    deadline = time.monotonic() + 35
    while mode() == "before":
        if time.monotonic() > deadline:
            raise RuntimeError("Owned legacy barrier deadline")
        time.sleep(.03)


async def main():
    await DatabaseLoader().ensure_country_exists(CODE)
    print("BATCH11_LEGACY_RETURN", flush=True)


asyncio.run(main())
