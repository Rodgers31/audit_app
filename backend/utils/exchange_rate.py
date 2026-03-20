"""Live USD/KES exchange rate utility with Redis caching."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FALLBACK_RATE = 129.0
CACHE_KEY = "exchange_rate:usd_kes"
CACHE_TTL = 86400  # 24 hours
FILE_CACHE_PATH = "/tmp/exchange_rate_cache.json"

PRIMARY_URL = "https://open.er-api.com/v6/latest/USD"
FALLBACK_URL = "https://api.exchangerate-api.com/v4/latest/USD"


def _get_redis_cache():
    """Lazy-load Redis cache to avoid import errors when redis is unavailable."""
    try:
        from cache.redis_cache import cache
        return cache
    except Exception:
        return None


def _read_file_cache() -> Optional[float]:
    """Read rate from file cache if not expired."""
    try:
        if not os.path.exists(FILE_CACHE_PATH):
            return None
        with open(FILE_CACHE_PATH) as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < CACHE_TTL:
            return float(data["rate"])
    except Exception:
        pass
    return None


def _write_file_cache(rate: float) -> None:
    """Write rate to file cache."""
    try:
        with open(FILE_CACHE_PATH, "w") as f:
            json.dump({"rate": rate, "timestamp": time.time()}, f)
    except Exception:
        pass


def _fetch_rate(url: str) -> Optional[float]:
    """Fetch KES rate from an exchange rate API endpoint."""
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rate = data.get("rates", {}).get("KES")
        if rate is not None:
            return float(rate)
        logger.warning("KES rate not found in response from %s", url)
    except Exception as e:
        logger.warning("Failed to fetch rate from %s: %s", url, e)
    return None


def get_usd_kes_rate() -> float:
    """Get the current USD to KES exchange rate.

    Checks Redis cache first (24h TTL), then file cache, then tries two free
    API endpoints, and falls back to a hardcoded rate if all else fails.
    """
    # Try Redis cache
    cache = _get_redis_cache()
    if cache is not None:
        try:
            cached = cache.get(CACHE_KEY)
            if cached is not None:
                return float(cached)
        except Exception:
            pass

    # Try file cache
    cached_file = _read_file_cache()
    if cached_file is not None:
        return cached_file

    # Try primary, then fallback API
    for url in (PRIMARY_URL, FALLBACK_URL):
        rate = _fetch_rate(url)
        if rate is not None:
            _write_file_cache(rate)
            if cache is not None:
                try:
                    cache.set(CACHE_KEY, rate, ttl=CACHE_TTL)
                except Exception:
                    pass
            logger.info("Cached USD/KES rate: %.2f from %s", rate, url)
            return rate

    logger.warning("All exchange rate APIs failed, using fallback rate %.2f", FALLBACK_RATE)
    return FALLBACK_RATE
