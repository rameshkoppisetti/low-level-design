import time
import threading
import heapq


# =========================
# READ WRITE LOCK
# =========================

class ReadWriteLock:
    def __init__(self):
        self._readers = 0
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()

    def acquire_read(self):
        with self._lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()

    def release_read(self):
        with self._lock:
            self._readers -= 1
            if self._readers == 0:
                self._write_lock.release()

    def acquire_write(self):
        self._write_lock.acquire()

    def release_write(self):
        self._write_lock.release()


# =========================
# KEY VALUE STORE
# =========================

class KeyValueStore:

    def __init__(self):
        self.map = {}  # key → (value, expiry_time)
        self.heap = []  # (expiry_time, key)
        self.lock = ReadWriteLock()

        self._stop = False
        self.cleaner = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleaner.start()

    # =========================
    # PUT
    # =========================
    def put(self, key, value, ttl):
        expiry = time.monotonic() + ttl

        self.lock.acquire_write()
        try:
            self.map[key] = (value, expiry)
            heapq.heappush(self.heap, (expiry, key))
        finally:
            self.lock.release_write()

    # =========================
    # GET
    # =========================
    def get(self, key):
        self.lock.acquire_read()
        try:
            if key not in self.map:
                return None

            value, expiry = self.map[key]

            # lazy expiration
            if expiry < time.monotonic():
                self.lock.release_read()

                self.lock.acquire_write()
                try:
                    if key in self.map:
                        del self.map[key]
                finally:
                    self.lock.release_write()

                return None

            return value
        finally:
            # ensure read lock released if not already
            try:
                self.lock.release_read()
            except:
                pass

    # =========================
    # DELETE
    # =========================
    def delete(self, key):
        self.lock.acquire_write()
        try:
            if key in self.map:
                del self.map[key]
        finally:
            self.lock.release_write()

    # =========================
    # BACKGROUND CLEANUP
    # =========================
    def _cleanup_worker(self):
        while not self._stop:
            now = time.monotonic()

            self.lock.acquire_write()
            try:
                while self.heap and self.heap[0][0] <= now:
                    expiry, key = heapq.heappop(self.heap)

                    # stale entry check
                    if key in self.map and self.map[key][1] == expiry:
                        del self.map[key]
            finally:
                self.lock.release_write()

            time.sleep(0.1)

    def stop(self):
        self._stop = True
        self.cleaner.join()


# =========================
# DEMO
# =========================

def main():
    store = KeyValueStore()

    store.put("a", 100, ttl=2)
    print(store.get("a"))  # 100

    time.sleep(3)
    print(store.get("a"))  # None (expired)

    store.put("b", 200, ttl=5)
    print(store.get("b"))  # 200

    store.stop()


if __name__ == "__main__":
    main()