"""Seeding package providing data ingestion utilities for the backend."""

# Lazy imports to avoid dependency chain failures during test collection.
# Use direct submodule imports (e.g. from seeding.config import ...) in production code.

__all__ = ["SeedingSettings", "get_settings", "SeedingHttpClient", "create_http_client"]


def __getattr__(name):
    if name in ("SeedingSettings", "get_settings"):
        from .config import SeedingSettings, get_settings
        globals()["SeedingSettings"] = SeedingSettings
        globals()["get_settings"] = get_settings
        return globals()[name]
    if name in ("SeedingHttpClient", "create_http_client"):
        from .http_client import SeedingHttpClient, create_http_client
        globals()["SeedingHttpClient"] = SeedingHttpClient
        globals()["create_http_client"] = create_http_client
        return globals()[name]
    raise AttributeError(f"module 'seeding' has no attribute {name!r}")
