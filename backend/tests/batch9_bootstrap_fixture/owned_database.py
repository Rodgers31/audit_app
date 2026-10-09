"""Connection authority for this lane's disposable PostgreSQL fixtures."""
import os
import re

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

TARGETS = {
    55492: ("batch9_bootstrap", "batch9-inert-local", "batch9-bootstrap-", "batch9-bootstrap-1183-db"),
    55590: ("batch9_review_590", "batch9-review-590-inert", "batch9-review-590-", "batch9-review-590-db"),
}


def owned_url(raw, *, allow_schema=False):
    try:
        url = make_url(raw)
        user, password, prefix, _ = TARGETS[url.port]
        valid = (url.drivername in {"postgresql", "postgresql+psycopg2"}
                 and url.host == "127.0.0.1" and url.username == user
                 and url.password == password and url.database is not None
                 and url.database.startswith(prefix)
                 and re.fullmatch(r"[a-z0-9-]{1,63}", url.database))
        if not valid:
            raise ValueError()
        if url.query:
            options = url.query.get("options")
            if not (allow_schema and set(url.query) == {"options"}
                    and isinstance(options, str)
                    and re.fullmatch(r"-csearch_path=(?:bootstrap|spec|adversarial)_[0-9a-f]{32}", options)):
                raise ValueError()
        if any(name.startswith("PG") and value for name, value in os.environ.items()):
            raise ValueError()
        return url.set(drivername="postgresql+psycopg2")
    except (ValueError, TypeError, KeyError):
        raise ValueError("Expected an owned bootstrap database without libpq redirects") from None


def owned_engine(raw, *, allow_schema=False, **kwargs):
    url = owned_url(raw, allow_schema=allow_schema)
    return create_engine(url, connect_args={
        "host": "127.0.0.1", "hostaddr": "127.0.0.1", "port": url.port,
        "dbname": url.database, "user": url.username, "password": url.password,
        "sslmode": "disable", "gssencmode": "disable", "connect_timeout": 8,
    }, **kwargs)


def schema_url(raw, schema):
    if not re.fullmatch(r"(?:bootstrap|spec|adversarial)_[0-9a-f]{32}", schema):
        raise ValueError("Expected an owned bootstrap schema")
    return owned_url(raw).update_query_dict({"options": f"-csearch_path={schema}"})
