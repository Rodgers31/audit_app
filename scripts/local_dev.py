#!/usr/bin/env python3
"""Isolated local UI workflow. No repository .env file is loaded."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PORT = 18080
FRONTEND_PORT = 13080
POSTGRES_PORT = 55432
POSTGRES_URL = (
    f"postgresql://auditgava_dev:auditgava_dev@127.0.0.1:{POSTGRES_PORT}/"
    "auditgava_local_dev?application_name=auditgava-local-dev-api"
)
PRIVATE_ENV_FILES = (
    ROOT / ".env", ROOT / "backend/.env", ROOT / "frontend/.env",
    ROOT / "frontend/.env.local", ROOT / "frontend/.env.development",
    ROOT / "frontend/.env.development.local",
)
TARGETS = {
    "DATABASE_URL": None,
    "DB_HOST": {"localhost", "127.0.0.1", "::1"},
    "PGHOST": {"localhost", "127.0.0.1", "::1"},
    "PGHOSTADDR": {"127.0.0.1", "::1"},
    "NEXT_PUBLIC_API_URL": {f"http://127.0.0.1:{API_PORT}", f"http://localhost:{API_PORT}"},
    "NEXT_PUBLIC_SUPABASE_URL": {f"http://127.0.0.1:{API_PORT}", f"http://localhost:{API_PORT}"},
}


def check_environment():
    for name, accepted in TARGETS.items():
        value = os.environ.get(name)
        if not value:
            continue
        if name == "DATABASE_URL":
            if value == POSTGRES_URL:
                continue
        elif value in accepted:
            continue
        raise ValueError(f"Refusing inherited remote or unapproved {name}; start from a clean shell")
    for path in PRIVATE_ENV_FILES:
        if path.exists():
            raise ValueError(f"Refusing private env file in this checkout: {path}")


def clean_environment(data_dir):
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("SUPABASE_", "NEXT_PUBLIC_", "DB_", "PG")):
            env.pop(name)
    for name in ("DATABASE_URL", "NEXT_PUBLIC_API_URL", "REDIS_URL", "SENTRY_DSN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        env.pop(name, None)
    env.update(
        ENVIRONMENT="development", AUTO_SEEDER_ENABLED="false",
        AUTO_WARMUP_ENABLED="false", REDIS_URL="",
        CORS_ORIGINS=f"http://127.0.0.1:{FRONTEND_PORT},http://localhost:{FRONTEND_PORT}",
        LOCAL_DEV_CORS_ORIGINS=f"http://127.0.0.1:{FRONTEND_PORT},http://localhost:{FRONTEND_PORT}",
        CACHE_GENERATION_FILE=str(data_dir / "cache-generation"),
        NEXT_PUBLIC_API_URL=f"http://127.0.0.1:{API_PORT}",
        NEXT_PUBLIC_SUPABASE_URL=f"http://127.0.0.1:{API_PORT}",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="local-dev-only-no-auth",
        FRONTEND_URL=f"http://127.0.0.1:{FRONTEND_PORT}",
    )
    return env


def run_api(database, data_dir):
    env = clean_environment(data_dir)
    if database == "sqlite":
        env["AUDIT_BROWSER_FIXTURE_DB"] = str(data_dir / "acceptance.sqlite")
        env["AUDIT_BROWSER_FIXTURE_PORT"] = str(API_PORT)
        command = [sys.executable, str(ROOT / "backend/tests/browser_fixture_api.py")]
        print(f"Synthetic acceptance API: http://127.0.0.1:{API_PORT} (persistent SQLite)", flush=True)
        return subprocess.call(command, cwd=ROOT, env=env)

    env["DATABASE_URL"] = POSTGRES_URL
    command = [sys.executable, str(ROOT / "backend/dev_postgres_api.py")]
    print(f"Synthetic acceptance API: http://127.0.0.1:{API_PORT} (local PostgreSQL)", flush=True)
    return subprocess.call(command, cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "db-up", "api", "frontend"))
    parser.add_argument("--db", choices=("sqlite", "postgres"), default="sqlite")
    args = parser.parse_args()
    try:
        check_environment()
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    data_dir = Path(os.environ.get("LOCAL_DEV_DATA_DIR", ROOT / ".local-dev")).resolve()
    if args.command == "check":
        print(f"Local targets verified: API {API_PORT}, frontend {FRONTEND_PORT}, PostgreSQL {POSTGRES_PORT}")
        return 0
    data_dir.mkdir(parents=True, exist_ok=True)
    env = clean_environment(data_dir)
    if args.command == "db-up":
        return subprocess.call(
            ["docker", "compose", "-f", "docker-compose.dev.yml", "-p", "auditgava-local-dev", "up", "-d", "--wait", "postgres"],
            cwd=ROOT, env=env,
        )
    if args.command == "api":
        return run_api(args.db, data_dir)
    return subprocess.call(
        ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(FRONTEND_PORT)],
        cwd=ROOT / "frontend", env=env,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
