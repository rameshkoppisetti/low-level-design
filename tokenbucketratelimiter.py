from abc import ABC, abstractmethod
import threading
import time


# =========================
# INTERFACE
# =========================

class RateLimiter(ABC):
    @abstractmethod
    def allow_request(self, user_id: str) -> bool:
        pass


# =========================
# THREAD-SAFE MAP
# =========================

class ThreadSafeDict:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get_or_create(self, key, factory):
        with self._lock:
            if key not in self._data:
                self._data[key] = factory()
            return self._data[key]


# =========================
# TOKEN BUCKET
# =========================

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate

        self.last_refill_time = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill_time

        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)

        self.last_refill_time = now

    def try_consume(self) -> bool:
        with self._lock:
            self._refill()

            if self.tokens >= 1:
                self.tokens -= 1
                return True

            return False


# =========================
# RATE LIMITER IMPLEMENTATION
# =========================

class TokenBucketRateLimiter(RateLimiter):
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets = ThreadSafeDict()

    def allow_request(self, user_id: str) -> bool:
        bucket = self._buckets.get_or_create(
            user_id,
            lambda: TokenBucket(self.capacity, self.refill_rate)
        )
        return bucket.try_consume()


# =========================
# DEMO
# =========================

def main():
    limiter = TokenBucketRateLimiter(capacity=5, refill_rate=2)
    user_id = "123"

    for _ in range(10):
        print(limiter.allow_request(user_id))
        time.sleep(0.2)


if __name__ == "__main__":
    main()