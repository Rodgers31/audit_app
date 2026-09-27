"""Enhanced database configuration with connection pooling and optimization."""

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from db_url import with_explicit_driver

load_dotenv()


def _build_db_url_from_env() -> str:
    """Build a SQLAlchemy Postgres URL from discrete env vars when DATABASE_URL is not set."""
    direct_url = os.getenv("DATABASE_URL")
    if direct_url:
        return direct_url

    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "6543")
    name = os.getenv("DB_NAME", "postgres")
    sslmode = os.getenv("DB_SSLMODE", "require")

    if user and host:
        pwd = quote_plus(password) if password else ""
        auth = f"{user}:{pwd}@" if user else ""
        return f"postgresql://{auth}{host}:{port}/{name}?sslmode={sslmode}"

    return "postgresql://postgres:password@localhost:5432/audit_app"


# Database configuration with connection pooling
DATABASE_URL = with_explicit_driver(_build_db_url_from_env())

# Enhanced engine configuration for production
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "40")),
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL queries in dev
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=utc",
    },
)

# Session configuration
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Connection pool event listeners for monitoring
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections."""
    import logging

    logger = logging.getLogger(__name__)
    logger.debug("New database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log connection checkouts from pool."""
    import logging

    logger = logging.getLogger(__name__)
    logger.debug("Connection checked out from pool")


def get_db():
    """Database dependency for FastAPI with proper cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables."""
    from models import Base

    Base.metadata.create_all(bind=engine)


def get_pool_status():
    """Get current connection pool status for monitoring."""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow(),
    }
