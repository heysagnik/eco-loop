
import threading
import time


class TokenBucket:
    def __init__(self, capacity: float, refill_per_minute: float) -> None:
        self._capacity = capacity
        self._tokens = float(capacity)
        self._refill_per_second = refill_per_minute / 60.0
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
        self._last_refill = now

    def try_acquire(self, amount: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens < amount:
                return False
            self._tokens -= amount
            return True

    def adjust(self, delta: float) -> None:
        
        with self._lock:
            self._refill()
            self._tokens = max(0.0, min(self._capacity, self._tokens + delta))
