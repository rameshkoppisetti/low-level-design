from collections import deque
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
# SLIDING WINDOW
# =========================

class SlidingWindow:
    def __init__(self, capacity: int, window_size: float):
        self.capacity = capacity
        self.window_size = window_size
        self.timestamps = deque()
        self._lock = threading.Lock()

    def try_consume(self) -> bool:
        with self._lock:
            now = time.monotonic()

            # remove expired
            while self.timestamps and now - self.timestamps[0] > self.window_size:
                self.timestamps.popleft()

            if len(self.timestamps) < self.capacity:
                self.timestamps.append(now)
                return True

            return False
        
        
# =========================
# RATE LIMITER IMPLEMENTATION
# =========================
       
class SlidingWindowRateLimiter(RateLimiter):
    def __init__(self, capacity, window_size):
        self.capacity = capacity
        self.window_size = window_size
        self._buckets = ThreadSafeDict()

    def allow_request(self, user_id):
        bucket = self._buckets.get_or_create(
            user_id,
            lambda: SlidingWindow(self.capacity, self.window_size)
        )
        return bucket.try_consume()
    

# =========================
# DEMO
# =========================

def main():
    limiter = SlidingWindowRateLimiter(capacity=5, refill_rate=2)
    user_id = "123"

    for _ in range(10):
        print(limiter.allow_request(user_id))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
    