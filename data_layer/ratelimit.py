import math
import threading
import time
from collections import deque

LIVE = "live"
BULK = "bulk"


# TODO: this limiter is per-process; running two tools at once can jointly exceed the key's limits. A shared
#  limiter (e.g. timestamps in the SQLite store) would fix that; 429s are still handled via Retry-After meanwhile.
class RateLimiter:
    """Sliding-window limiter over several (count, seconds) windows.

    Bulk callers stop short of each cap by `bulk_reserve`, so live lookups always have headroom.
    """

    def __init__(self, windows, bulk_reserve=0.2, clock=time.monotonic, sleep=time.sleep):
        self._windows = [(count, seconds, deque()) for count, seconds in windows]
        self._reserve = bulk_reserve
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def _cap(self, limit, priority):
        if priority == LIVE:
            return limit
        return max(1, limit - math.ceil(limit * self._reserve))

    def _wait_needed(self, now, priority):
        wait = self._blocked_until - now
        for limit, seconds, stamps in self._windows:
            while stamps and stamps[0] <= now - seconds:
                stamps.popleft()
            cap = self._cap(limit, priority)
            if len(stamps) >= cap:
                wait = max(wait, stamps[len(stamps) - cap] + seconds - now)
        return wait

    def acquire(self, priority=BULK):
        while True:
            with self._lock:
                now = self._clock()
                wait = self._wait_needed(now, priority)
                if wait <= 0:
                    for _, _, stamps in self._windows:
                        stamps.append(now)
                    return
            self._sleep(wait + 0.01)

    def block_for(self, seconds):
        with self._lock:
            self._blocked_until = max(self._blocked_until, self._clock() + seconds)
