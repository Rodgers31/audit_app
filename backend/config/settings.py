"""Application configuration and settings."""

import os
import secrets as stdlib_secrets
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .secrets import get_secret


class Settings(BaseSettings):
    """Application settings with validation."""

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # Ignore unrelated env vars (e.g., DB_* when using DATABASE_URL)
    )

    # Application
    APP_NAME: str = "Kenya Audit Transparency API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Secret Management Backend
    SECRET_BACKEND: str = "env"  # Options: "env", "aws", "vault"

    # Security - Use secret manager for sensitive values
    @property
    def SECRET_KEY(self) -> str:
        """Get secret key from secret manager or generate one."""
        key = get_secret("SECRET_KEY")
        if not key:
            # Generate and warn in production
            key = stdlib_secrets.token_urlsafe(32)
            if self.ENVIRONMENT == "production":
                import logging

                logging.warning(
                    "SECRET_KEY not in secret manager, using generated key (not persistent!)"
                )
        return key

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS – accepts JSON array '["https://a.com"]' OR comma-separated 'https://a.com,https://b.com'
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "https://audit-app-4pwa.onrender.com",
        "https://audit-app-frontend.onrender.com",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        origins: list[str] = []
        if isinstance(v, list):
            origins = v
        elif isinstance(v, str):
            # Try JSON first, fallback to comma-separated
            import json

            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    origins = [s.strip() for s in parsed if s.strip()]
            except (json.JSONDecodeError, TypeError):
                origins = [s.strip() for s in v.split(",") if s.strip()]
        else:
            return v  # type: ignore

        # Auto-expand www / non-www variants so CORS never silently fails
        expanded: set[str] = set()
        for o in origins:
            expanded.add(o)
            from urllib.parse import urlparse

            parsed_url = urlparse(o)
            host = parsed_url.hostname or ""
            if host.startswith("www."):
                # Add non-www variant
                bare = o.replace("://www.", "://", 1)
                expanded.add(bare)
            elif host and "localhost" not in host:
                # Add www variant
                expanded.add(o.replace("://", "://www.", 1))
        return list(expanded)

    # Database connection parameters (optional - can use individual params or DATABASE_URL)
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[str] = None
    DB_NAME: Optional[str] = None
    DB_SSLMODE: Optional[str] = None

    # Database - Use secret manager for credentials
    @property
    def DATABASE_URL(self) -> str:
        """Get database URL from secret manager, env, or construct from components."""
        # First, try to get complete DATABASE_URL
        db_url = get_secret("DATABASE_URL", os.getenv("DATABASE_URL"))

        if db_url:
            return db_url

        # If not found, try to construct from individual components
        if self.DB_USER and self.DB_PASSWORD and self.DB_HOST and self.DB_NAME:
            port = self.DB_PORT or "5432"
            sslmode = f"?sslmode={self.DB_SSLMODE}" if self.DB_SSLMODE else ""
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{port}/{self.DB_NAME}{sslmode}"

        # Fallback to default
        return "postgresql://postgres:password@localhost:5432/audit_app"

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # Redis
    @property
    def REDIS_URL(self) -> str:
        """Get Redis URL from secret manager or env."""
        return get_secret("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379"))

    CACHE_TTL: int = 3600  # 1 hour default

    # Rate Limiting
    RATE_LIMIT_CALLS: int = 100
    RATE_LIMIT_PERIOD: int = 60  # seconds

    # Monitoring
    @property
    def SENTRY_DSN(self) -> Optional[str]:
        """Get Sentry DSN from secret manager."""
        return get_secret("SENTRY_DSN", os.getenv("SENTRY_DSN", ""))

    LOG_LEVEL: str = "INFO"

    # ETL
    ETL_SCHEDULE_CRON: str = "0 2 * * *"  # 2 AM daily

    # AWS S3 (optional) - credentials from secret manager
    @property
    def AWS_ACCESS_KEY_ID(self) -> str:
        return get_secret("AWS_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID", ""))

    @property
    def AWS_SECRET_ACCESS_KEY(self) -> str:
        return get_secret(
            "AWS_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY", "")
        )

    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"

    # Email (optional) - credentials from secret manager
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""

    @property
    def SMTP_PASSWORD(self) -> str:
        return get_secret("SMTP_PASSWORD", os.getenv("SMTP_PASSWORD", ""))

    SMTP_FROM: str = ""

    # Frontend URL — used for building links in emails (unsubscribe, etc.)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Note: Pydantic v2 uses model_config above instead of inner Config


# Global settings instance
settings = Settings()
