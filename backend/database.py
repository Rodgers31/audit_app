import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()


def _build_db_url_from_env() -> str:
    """Build a SQLAlchemy Postgres URL from discrete env vars when DATABASE_URL is not set.

    Supported variables:
      - DB_USER
      - DB_PASSWORD
      - DB_HOST
      - DB_PORT (default 6543 for Supabase Transaction Pooler)
      - DB_NAME (default postgres)
      - DB_SSLMODE (default require)
    Falls back to localhost dev URL if nothing is provided.
    """
    # If DATABASE_URL explicitly provided, use it as-is
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

    # Fallback dev URL
    return "postgresql://postgres:password@localhost:5432/audit_app"


# Database configuration
DATABASE_URL = _build_db_url_from_env()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,        # Supabase transaction pooler allows ~15 concurrent connections;
    max_overflow=10,    # keep headroom for migrations, seeding, and other clients
    pool_recycle=300,   # recycle connections every 5 min (Supabase may drop idle ones)
    pool_timeout=30,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Database dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables."""
    from models import Base

    Base.metadata.create_all(bind=engine)
