"""Redis client utilities."""

from __future__ import annotations

import logging

import redis

logger = logging.getLogger(__name__)


def get_redis_connection(redis_url: str) -> redis.Redis:
    """Create a Redis client from a connection URL."""

    try:
        return redis.Redis.from_url(redis_url, decode_responses=False)
    except redis.RedisError as exc:  # pragma: no cover - network dependency
        logger.error("Unable to connect to Redis at %s", redis_url)
        raise
