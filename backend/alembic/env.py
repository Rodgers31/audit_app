import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Load .env so DATABASE_URL is available when running alembic CLI
if load_dotenv is not None:
    here = Path(__file__).resolve().parent
    for env_path in [here.parent / ".env", here.parent.parent / ".env"]:
        if env_path.exists():
            load_dotenv(env_path.as_posix(), override=False)

from models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# ── Production drift that migrations do not manage ───────────────────
# The production database predates the rebaselined chain and contains
# objects the ORM never owned. `alembic check` (autogenerate) would
# propose dropping them, which makes its output useless as the
# "does live schema match the baseline?" gate the baseline docstring
# prescribes. Each exclusion below was verified against a pg_dump clone
# of production on 2026-08-29 — see git history for the diff.
#
# Tables created directly in Supabase (SQL editor / dashboard), not by
# models.py:
_NON_MODEL_TABLES = {
    "profiles",  # Supabase auth profile mirror (uuid PK)
    "validation_failures",  # pre-baseline ETL quarantine table
}
# Columns that exist in production on model-managed tables but not in
# models.py. All verified empty or Supabase-managed; retained, not
# dropped, and excluded from autogenerate comparison:
_NON_MODEL_COLUMNS = {
    ("audits", "validation_warnings"),  # jsonb, pre-baseline validator
    ("budget_lines", "validation_warnings"),  # jsonb, pre-baseline validator
    ("population_data", "total_population"),  # pre-baseline census shape
    ("population_data", "male_population"),
    ("population_data", "female_population"),
    ("population_data", "urban_population"),
    ("population_data", "rural_population"),
}


def _include_object(obj, name, type_, reflected, compare_to):
    """Filter reflected-but-unmanaged objects out of autogenerate/check."""
    if type_ == "table" and reflected and name in _NON_MODEL_TABLES:
        return False
    if (
        type_ == "column"
        and reflected
        and compare_to is None
        and (obj.table.name, name) in _NON_MODEL_COLUMNS
    ):
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # Prefer environment variable and escape % for ConfigParser
    url = os.getenv("DATABASE_URL")
    if not url:
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST")
        port = os.getenv("DB_PORT", "6543")
        name = os.getenv("DB_NAME", "postgres")
        sslmode = os.getenv("DB_SSLMODE", "require")
        if user and host:
            from urllib.parse import quote_plus

            pwd = quote_plus(password) if password else ""
            auth = f"{user}:{pwd}@"
            url = f"postgresql://{auth}{host}:{port}/{name}?sslmode={sslmode}"
        else:
            url = config.get_main_option("sqlalchemy.url")
    if "%" in url:
        url = url.replace("%", "%%")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # Override with environment variable if present
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST")
        port = os.getenv("DB_PORT", "6543")
        name = os.getenv("DB_NAME", "postgres")
        sslmode = os.getenv("DB_SSLMODE", "require")
        if user and host:
            from urllib.parse import quote_plus

            pwd = quote_plus(password) if password else ""
            auth = f"{user}:{pwd}@"
            database_url = f"postgresql://{auth}{host}:{port}/{name}?sslmode={sslmode}"
        else:
            database_url = config.get_main_option("sqlalchemy.url")
    # Escape % to avoid ConfigParser interpolation errors
    if "%" in database_url:
        database_url = database_url.replace("%", "%%")
    config.set_main_option("sqlalchemy.url", database_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
