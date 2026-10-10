"""Owned fixture inputs and a shared publishing boundary for active receipts.

This is a local verification helper, never an operator credential provider.
Arbitrary environment overrides are private inputs; only explicitly public
execution settings are serialized. Commands, errors and console output cross
the same redaction boundary as JSON and Markdown.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit

PUBLIC_ENV = frozenset({"PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHON_DOTENV_DISABLED"})
DATABASE_ENV = frozenset({"DATABASE_URL", "BATCH9_RECONCILIATION_DATABASE_URL", "AUDIT_RECONCILIATION_DIRECT_DATABASE_URL"})
URL_PATTERN = re.compile(r"\b(?:postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?|mysql(?:\+[A-Za-z0-9_]+)?|redis|rediss)://[^\s\"'<>]+", re.IGNORECASE)


def owned_url(value):
    try:
        parsed = urlsplit(value)
        valid = (type(value) is str and parsed.scheme in ("postgresql", "postgresql+psycopg2")
                 and parsed.hostname == "127.0.0.1" and parsed.port is not None
                 and 1024 <= parsed.port <= 65535 and not parsed.query and not parsed.fragment
                 and re.fullmatch(r"/(?:batch9-reconciliation-|batch9-review-592-)[a-zA-Z0-9_-]+", parsed.path))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Explicit owned loopback reconciliation target required")
    return value


def owned_environment(root):
    url = owned_url(os.environ.get("BATCH9_RECONCILIATION_DATABASE_URL"))
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(root / "backend"),
           "DATABASE_URL": url, "BATCH9_RECONCILIATION_DATABASE_URL": url}
    try:
        overrides = json.loads(os.environ.get("BATCH9_RECEIPT_ENV", "{}"))
    except (ValueError, TypeError):
        raise ValueError("Malformed owned receipt environment") from None
    if type(overrides) is not dict or any(type(k) is not str or type(v) is not str for k, v in overrides.items()):
        raise ValueError("Malformed owned receipt environment")
    if any(k in DATABASE_ENV and v != url for k, v in overrides.items()):
        raise ValueError("Connection overrides must equal the explicit owned target")
    env.update(overrides)
    return env


def redact(value, environment):
    """Remove private input values and connection URLs from nested publications."""
    secrets = set()
    for key, raw in environment.items():
        if key not in PUBLIC_ENV and isinstance(raw, str) and raw:
            secrets.add(raw)
            secrets.add(json.dumps(raw, ensure_ascii=True)[1:-1])
        if key in DATABASE_ENV and isinstance(raw, str):
            try:
                password = urlsplit(raw).password
                if password:
                    secrets.update((password, unquote(password), quote(unquote(password), safe="")))
            except ValueError:
                pass
    ordered = sorted(secrets, key=len, reverse=True)

    def visit(item):
        if isinstance(item, str):
            for secret in ordered:
                # Short private values must not corrupt digests/path segments
                # merely because one character occurs inside them.
                item = (item.replace(secret, "[REDACTED]") if len(secret) >= 8 else
                        re.sub(r"(?<!\w)" + re.escape(secret) + r"(?!\w)", "[REDACTED]", item))
            return URL_PATTERN.sub("[REDACTED_DATABASE_URL]", item)
        if isinstance(item, dict):
            return {visit(k): visit(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [visit(v) for v in item]
        return item

    return visit(value)


def public_environment(environment):
    return {key: redact(value, environment) if key in PUBLIC_ENV else "[REDACTED]"
            for key, value in environment.items()}


def safety_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
