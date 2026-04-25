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
# LEAKY BUCKET
# =========================

class LeakyBucket:
    def __init__(self, capacity: int, leak_rate: float):
        self.capacity = capacity
        self.current_water = 0.0
        self.leak_rate = leak_rate

        self.last_leak_time = time.monotonic()
        self._lock = threading.Lock()

    def _leak(self):
        now = time.monotonic()
        elapsed = now - self.last_leak_time

        leaked = elapsed * self.leak_rate
        self.current_water = max(0.0, self.current_water - leaked)

        self.last_leak_time = now

    def try_consume(self) -> bool:
        with self._lock:
            self._leak()

            if self.current_water + 1 <= self.capacity:
                self.current_water += 1
                return True

            return False

# =========================
# RATE LIMITER IMPLEMENTATION
# =========================

class LeakyBucketRateLimiter(RateLimiter):
    def __init__(self, capacity, leak_rate):
        self.capacity = capacity
        self.leak_rate = leak_rate
        self._buckets = ThreadSafeDict()

    def allow_request(self, user_id):
        bucket = self._buckets.get_or_create(
            user_id,
            lambda: LeakyBucket(self.capacity, self.leak_rate)
        )
        return bucket.try_consume()
    
        
        
# =========================
# DEMO
# =========================

def main():
    limiter = LeakyBucketRateLimiter(capacity=5, refill_rate=2)
    user_id = "123"

    for _ in range(10):
        print(limiter.allow_request(user_id))
        time.sleep(0.2)


if __name__ == "__main__":
    main()