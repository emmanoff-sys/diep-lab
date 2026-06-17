"""Redis client construction — Phase 22 K4 production rollout.

Gated by REDIS_SENTINELS (comma-separated host:port pairs, e.g.
"diep-redis-sentinel-1:26379,diep-redis-sentinel-2:26379,diep-redis-sentinel-3:26379").
Unset/empty keeps the pre-K4 direct connection to diep-redis unchanged — the
instant-rollback path called for in K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md §6.
"""
import os

import redis
import redis.sentinel


def get_redis_client(decode_responses: bool = True) -> redis.Redis:
    password = os.getenv("REDIS_PASSWORD") or None
    sentinels_env = os.getenv("REDIS_SENTINELS", "")
    if sentinels_env:
        hosts = []
        for entry in sentinels_env.split(","):
            host, port = entry.strip().split(":")
            hosts.append((host, int(port)))
        sentinel = redis.sentinel.Sentinel(
            hosts, sentinel_kwargs={"password": password} if password else {}
        )
        return sentinel.master_for(
            "diep-master", password=password, decode_responses=decode_responses
        )
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "diep-redis"), port=6379,
        password=password, decode_responses=decode_responses,
    )
