import threading
import time
import string


# ---------------- MODEL ----------------
class URLMapping:
    def __init__(self, short_code, long_url, expiry=None):
        self.short_code = short_code
        self.long_url = long_url
        self.expiry = expiry


# ---------------- ID GENERATOR ----------------
class IdGenerator:
    def __init__(self):
        self.counter = 0
        self.lock = threading.Lock()
        self.base62 = string.ascii_letters + string.digits

    def generate(self):
        with self.lock:
            self.counter += 1
            return self._encode(self.counter)

    def _encode(self, num):
        base = len(self.base62)
        res = []
        while num > 0:
            res.append(self.base62[num % base])
            num //= base
        return ''.join(reversed(res))


# ---------------- IN-MEMORY STORE ----------------
class URLStore:
    def __init__(self):
        self.store = {}
        self.lock = threading.Lock()

    def save(self, mapping):
        with self.lock:
            self.store[mapping.short_code] = mapping

    def get(self, short_code):
        with self.lock:
            return self.store.get(short_code)


# ---------------- SERVICE ----------------
class URLShortenerService:
    def __init__(self):
        self.store = URLStore()
        self.id_gen = IdGenerator()

    def create_short_url(self, long_url, ttl=None):
        short_code = self.id_gen.generate()
        expiry = time.time() + ttl if ttl else None

        mapping = URLMapping(short_code, long_url, expiry)
        self.store.save(mapping)

        return short_code

    def get_long_url(self, short_code):
        mapping = self.store.get(short_code)
        if not mapping:
            return None

        if mapping.expiry and mapping.expiry < time.time():
            return None

        return mapping.long_url


# ---------------- DEMO ----------------
if __name__ == "__main__":
    service = URLShortenerService()

    short = service.create_short_url("https://google.com", ttl=5)
    print("Short:", short)

    print("Redirect:", service.get_long_url(short))