from collections import deque
from enum import Enum
import time


class State(Enum):
    CLOSED = 1
    OPEN = 2
    HALF_OPEN = 3


class CircuitBreakerOpen(Exception):
    pass


class CircuitBreaker:

    def __init__(self, failure_threshold, window_seconds, reset_timeout):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.reset_timeout = reset_timeout

        self.state = State.CLOSED
        self.failure_times = deque()
        self.opened_at = None

    def _cleanup_old_failures(self):
        now = time.time()

        while (self.failure_times and
               now - self.failure_times[0] > self.window_seconds):
            self.failure_times.popleft()

    def _record_failure(self):
        now = time.time()

        self.failure_times.append(now)
        self._cleanup_old_failures()

        if len(self.failure_times) >= self.failure_threshold:
            self.state = State.OPEN
            self.opened_at = now

    def _record_success(self):
        self.failure_times.clear()
        self.state = State.CLOSED

    def call(self, func, *args, **kwargs):

        now = time.time()

        if self.state == State.OPEN:
            if now - self.opened_at >= self.reset_timeout:
                self.state = State.HALF_OPEN
            else:
                raise CircuitBreakerOpen("Circuit is OPEN")

        try:
            result = func(*args, **kwargs)

            self._record_success()

            return result

        except Exception:
            self._record_failure()

            if self.state == State.HALF_OPEN:
                self.state = State.OPEN
                self.opened_at = now

            raise


cb = CircuitBreaker(
    failure_threshold=3,
    window_seconds=10,
    reset_timeout=5
)

count = 0

def service():
    global count
    count += 1
    raise Exception("Failure")

for _ in range(5):
    try:
        cb.call(service)
    except Exception as e:
        print(cb.state, e)
