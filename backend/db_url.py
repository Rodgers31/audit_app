"""Pin the Postgres DBAPI driver in a database URL.

A bare ``postgresql://`` URL leaves the driver choice to SQLAlchemy, and that
default moved: 2.0 picks psycopg2, 2.1 picks psycopg (v3). requirements.txt
ships psycopg2-binary only, so when an unpinned install pulled SQLAlchemy 2.1
every engine died at creation with ``No module named 'psycopg'`` and the
nightly seed stopped (issue #228).

Stdlib only: alembic/env.py imports this in CI jobs that install nothing but
alembic, sqlalchemy and psycopg2-binary.
"""

POSTGRES_DRIVER = "psycopg2"

# Schemes that name Postgres without naming a driver. ``postgres://`` is what
# Heroku-style providers hand out; SQLAlchemy >= 1.4 rejects it outright.
_DRIVERLESS_SCHEMES = {"postgres", "postgresql"}


def with_explicit_driver(url: str) -> str:
    """Return ``url`` with a driverless Postgres scheme rewritten to psycopg2.

    Only the scheme is touched, so credentials, host and query string
    (``sslmode``, ``options`` ...) come back byte-for-byte. A URL that already
    names a driver (``postgresql+psycopg2://``, ``postgresql+asyncpg://``) or
    another database (``sqlite://``) is returned unchanged.
    """
    scheme, sep, rest = url.partition("://")
    if sep and scheme.lower() in _DRIVERLESS_SCHEMES:
        return f"postgresql+{POSTGRES_DRIVER}://{rest}"
    return url
