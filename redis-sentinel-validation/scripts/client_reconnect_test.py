"""K4 Redis Sentinel validation — sentinel-aware client reconnection probe.

Mirrors the target production client pattern (redis.sentinel.Sentinel +
master_for) and continuously writes/reads a counter key, logging the
resolved master each iteration, so a failover shows up as a brief error
followed by reconnection to the newly promoted primary.
"""
import time

from redis.sentinel import Sentinel

PASSWORD = "redis-sentinel-validation-only"

sentinel = Sentinel(
    [
        ("diep-redis-val-sentinel-1", 26379),
        ("diep-redis-val-sentinel-2", 26379),
        ("diep-redis-val-sentinel-3", 26379),
    ],
    socket_timeout=0.5,
    sentinel_kwargs={"password": PASSWORD},
)

for i in range(120):
    t0 = time.monotonic()
    try:
        master = sentinel.master_for(
            "diep-val-master", password=PASSWORD, socket_timeout=0.5
        )
        master.set("client-reconnect-probe", i)
        val = master.get("client-reconnect-probe")
        addr = sentinel.discover_master("diep-val-master")
        print(f"{time.strftime('%H:%M:%S')} iter={i:02d} OK   master={addr} val={val} dt={time.monotonic()-t0:.3f}s")
    except Exception as exc:
        print(f"{time.strftime('%H:%M:%S')} iter={i:02d} FAIL master=?           err={exc!r} dt={time.monotonic()-t0:.3f}s")
    time.sleep(1)
