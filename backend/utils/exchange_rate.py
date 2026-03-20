"""Live USD/KES exchange rate utility with Redis caching."""

import logging

import httpx

from cache.redis_cache import cache

logger = logging.getLogger(__name__)

FALLBACK_RATE = 129.0
CACHE_KEY = "exchange_rate:usd_kes"
CACHE_TTL = 86400  # 24 hours

PRIMARY_URL = "https://open.er-api.com/v6/latest/USD"
FALLBACK_URL = "https://api.exchangerate-api.com/v4/latest/USD"


def _fetch_rate(url: str) -> float | None:
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

    Checks Redis cache first (24h TTL), then tries two free API endpoints,
    and falls back to a hardcoded rate if all else fails.
    """
    # Check cache
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return float(cached)

    # Try primary, then fallback API
    for url in (PRIMARY_URL, FALLBACK_URL):
        rate = _fetch_rate(url)
        if rate is not None:
            cache.set(CACHE_KEY, rate, ttl=CACHE_TTL)
            logger.info("Cached USD/KES rate: %.2f from %s", rate, url)
            return rate

    logger.warning("All exchange rate APIs failed, using fallback rate %.2f", FALLBACK_RATE)
    return FALLBACK_RATE
