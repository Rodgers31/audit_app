"""Explicit current queue/policy DDL for runtime tests, not historical DDL tests.

These helpers apply the real migrations to an already owned random schema.
Source-backed report authority requires the separate full application fixture.
No production verifier, role contract, source view or schema guard is replaced.
"""
from alembic.migration import MigrationContext
from alembic.operations import Operations


def add_current_worker_policy(engine):
    from test_connections_migration_postgres import _migration
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        _migration('a704b15a0001_social_generation_shadow.py').upgrade()
        _migration('a706b15a0001_social_policy_authority.py').upgrade()


def upgrade_current_social_runtime(engine):
    from test_connections_migration_postgres import upgrade
    upgrade(engine, current=True)
    add_current_worker_policy(engine)
