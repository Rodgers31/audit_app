"""The scoped cohort reuses the repo's SQLite JSONB compile setup only.

This matches backend/conftest.py without importing its application-wide fixtures.
PostgreSQL types and all epoch/provenance controls still use real PostgreSQL.
"""

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def compile_legacy_sqlite_jsonb(element, compiler, **kwargs):
    return "TEXT"
