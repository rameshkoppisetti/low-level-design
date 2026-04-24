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


# ---------------- STORE ----------------
class URLStore:
    def __init__(self):
        self.store = {}
        self.lock = threading.Lock()

    def exists(self, short_code):
        with self.lock:
            return short_code in self.store

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

    def create_short_url(self, long_url, custom_alias=None, ttl=None):
        # ---- CUSTOM ALIAS ----
        if custom_alias:
            if self.store.exists(custom_alias):
                raise Exception("Alias already exists")
            short_code = custom_alias
        else:
            # ---- GENERATE UNIQUE CODE ----
            while True:
                short_code = self.id_gen.generate()
                if not self.store.exists(short_code):
                    break  # collision avoided

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

    # normal
    short1 = service.create_short_url("https://google.com")
    print("Short1:", short1)

    # custom alias
    short2 = service.create_short_url("https://openai.com", custom_alias="openai")
    print("Short2:", short2)

    # collision test
    try:
        service.create_short_url("https://test.com", custom_alias="openai")
    except Exception as e:
        print("Collision:", e)

    print("Redirect:", service.get_long_url("openai"))