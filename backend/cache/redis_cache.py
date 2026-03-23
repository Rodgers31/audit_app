"""Redis caching utilities for API responses."""

import json
import logging
import os
import time
from functools import wraps
from typing import Any, Callable, Optional

import redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache manager with fallback to in-memory cache."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client: Optional[redis.Redis] = None
        self._memory_cache = {}  # {key: (value, expiry_timestamp)}
        self._memory_cache_max_size = 1024
        self._initialize()

    def _initialize(self):
        """Initialize Redis connection with error handling."""
        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self.client.ping()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.info(
                "Redis not configured — using in-memory cache (this is normal without a Redis add-on)"
            )
            self.client = None

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            if self.client:
                value = self.client.get(key)
                if value:
                    return json.loads(value)
            else:
                # Fallback to memory cache
                entry = self._memory_cache.get(key)
                if entry is not None:
                    value, expiry = entry
                    if time.time() < expiry:
                        return value
                    else:
                        del self._memory_cache[key]  # Expired
        except Exception as e:
            logger.error(f"Cache get error: {e}")
        return None

    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        try:
            if self.client:
                self.client.setex(key, ttl, json.dumps(value))
            else:
                # Fallback to memory cache with TTL
                if len(self._memory_cache) >= self._memory_cache_max_size:
                    # Evict expired entries first
                    now = time.time()
                    expired_keys = [k for k, (_, exp) in self._memory_cache.items() if now >= exp]
                    for k in expired_keys:
                        del self._memory_cache[k]
                    # If still full, evict oldest entry
                    if len(self._memory_cache) >= self._memory_cache_max_size:
                        oldest_key = next(iter(self._memory_cache))
                        del self._memory_cache[oldest_key]
                self._memory_cache[key] = (value, time.time() + ttl)
        except Exception as e:
            logger.error(f"Cache set error: {e}")

    def delete(self, key: str):
        """Delete key from cache."""
        try:
            if self.client:
                self.client.delete(key)
            else:
                self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")

    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern."""
        try:
            if self.client:
                keys = self.client.keys(pattern)
                if keys:
                    self.client.delete(*keys)
            else:
                # Memory cache - clear matching keys
                keys_to_delete = [
                    k for k in self._memory_cache if pattern.replace("*", "") in k
                ]
                for key in keys_to_delete:
                    self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

    def health_check(self) -> dict:
        """Check Redis health status."""
        try:
            if self.client:
                self.client.ping()
                info = self.client.info()
                return {
                    "status": "healthy",
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "uptime_seconds": info.get("uptime_in_seconds", 0),
                }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        return {
            "status": "unavailable" if self.client else "using_memory_cache",
            "message": "Using in-memory fallback cache",
        }


# Global cache instance
cache = RedisCache()


def cached(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key_parts = [key_prefix or func.__name__]

            # Add args to key
            for arg in args:
                cache_key_parts.append(str(arg))

            # Add kwargs to key
            for k, v in sorted(kwargs.items()):
                cache_key_parts.append(f"{k}={v}")

            cache_key = ":".join(cache_key_parts)

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Call function and cache result
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)

            if result is not None:
                cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def invalidate_cache(pattern: str):
    """Invalidate cache entries matching pattern."""
    cache.clear_pattern(pattern)
    logger.info(f"Invalidated cache pattern: {pattern}")
