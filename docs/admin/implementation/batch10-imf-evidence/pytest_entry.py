"""Run pytest with dotenv and all socket transports disabled before imports."""

import json
import os
import socket
import sys

import dotenv
from pydantic_settings.sources import DotEnvSettingsSource

dotenv.load_dotenv = lambda *args, **kwargs: False
DotEnvSettingsSource._read_env_files = lambda self: {}


def refuse_connect(self, address):
    raise OSError("batch10-imf verification blocks all socket connections")


socket.socket.connect = refuse_connect
socket.socket.connect_ex = refuse_connect
print(
    "batch10-imf runtime inputs: "
    + json.dumps(
        {
            key: os.environ[key]
            for key in (
                "DATABASE_URL",
                "REDIS_URL",
                "ENVIRONMENT",
                "SECRET_BACKEND",
                "AUTO_SEEDER_ENABLED",
                "AUTO_WARMUP_ENABLED",
                "PYTHON_DOTENV_DISABLED",
            )
        }
    ),
    flush=True,
)

import pytest

from config.settings import settings
import database
import main

if (
    database.DATABASE_URL != os.environ["DATABASE_URL"]
    or settings.DATABASE_URL != database.DATABASE_URL
):
    raise RuntimeError("Database configuration differs from the owned fixture")
if main.AUTO_SEEDER_ENABLED or main._WARMUP_ENABLED or not main.DATABASE_AVAILABLE:
    raise RuntimeError("Unexpected resolved application inputs")
print(
    "batch10-imf resolved inputs: "
    + json.dumps(
        {
            "database": database.DATABASE_URL,
            "redis": settings.REDIS_URL,
            "environment": settings.ENVIRONMENT,
            "database_available": main.DATABASE_AVAILABLE,
            "auto_seeder": main.AUTO_SEEDER_ENABLED,
            "auto_warmup": main._WARMUP_ENABLED,
            "dotenv_source": "disabled",
            "socket_transport": "blocked",
        }
    ),
    flush=True,
)

raise SystemExit(pytest.main(sys.argv[1:]))
