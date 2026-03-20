"""Seeding package providing data ingestion utilities for the backend."""

# Use try/except on individual imports to avoid poisoning the package namespace
# if optional dependencies (pydantic, httpx) are unavailable in minimal environments.
try:
    from .config import SeedingSettings, get_settings
except Exception:  # pragma: no cover
    SeedingSettings = None  # type: ignore[assignment,misc]
    get_settings = None  # type: ignore[assignment]

try:
    from .http_client import SeedingHttpClient, create_http_client
except Exception:  # pragma: no cover
    SeedingHttpClient = None  # type: ignore[assignment,misc]
    create_http_client = None  # type: ignore[assignment]

__all__ = ["SeedingSettings", "get_settings", "SeedingHttpClient", "create_http_client"]
