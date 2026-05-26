from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
import threading


# ------------------ STRATEGY INTERFACE ------------------
class EvictionStrategy(ABC):

    @abstractmethod
    def on_get(self, key): pass

    @abstractmethod
    def on_put(self, key): pass

    @abstractmethod
    def on_delete(self, key): pass

    @abstractmethod
    def evict(self): pass

    @abstractmethod
    def clear(self): pass


# ------------------ LRU ------------------
class LRUStrategy(EvictionStrategy):
    def __init__(self):
        self.order = OrderedDict()

    def on_get(self, key):
        self.order.move_to_end(key, last=False)

    def on_put(self, key):
        self.order[key] = None
        self.order.move_to_end(key, last=False)

    def on_delete(self, key):
        self.order.pop(key, None)

    def evict(self):
        if not self.order:
            return None
        key, _ = self.order.popitem(last=True)
        return key

    def clear(self):
        self.order.clear()


# ------------------ FIFO ------------------
class FIFOStrategy(EvictionStrategy):
    def __init__(self):
        self.order = OrderedDict()

    def on_get(self, key):
        pass  # no change

    def on_put(self, key):
        self.order[key] = None
        self.order.move_to_end(key, last=False)

    def on_delete(self, key):
        self.order.pop(key, None)

    def evict(self):
        if not self.order:
            return None
        key, _ = self.order.popitem(last=True)
        return key

    def clear(self):
        self.order.clear()


# ------------------ LFU ------------------
class LFUStrategy(EvictionStrategy):
    def __init__(self):
        self.freq_map = defaultdict(OrderedDict)
        self.key_freq = {}
        self.min_freq = 1

    def _update(self, key):
        freq = self.key_freq[key]
        self.freq_map[freq].pop(key, None)

        if not self.freq_map[freq] and freq == self.min_freq:
            self.min_freq += 1

        new_freq = freq + 1
        self.key_freq[key] = new_freq
        self.freq_map[new_freq][key] = None
        self.freq_map[new_freq].move_to_end(key, last=False)

    def on_get(self, key):
        self._update(key)

    def on_put(self, key):
        self.key_freq[key] = 1
        self.freq_map[1][key] = None
        self.freq_map[1].move_to_end(key, last=False)
        self.min_freq = 1

    def on_delete(self, key):
        freq = self.key_freq.pop(key, None)
        if freq is None:
            return
        self.freq_map[freq].pop(key, None)

        if freq == self.min_freq and not self.freq_map[freq]:
            self._refresh_min_freq()

    def evict(self):
        if not self.key_freq:
            return None

        keys = self.freq_map[self.min_freq]
        key, _ = keys.popitem(last=True)
        self.key_freq.pop(key, None)
        return key

    def clear(self):
        self.freq_map.clear()
        self.key_freq.clear()
        self.min_freq = 1

    def _refresh_min_freq(self):
        self.min_freq = min(
            (freq for freq, keys in self.freq_map.items() if keys),
            default=1,
        )


# ------------------ CACHE ------------------
class InMemoryCache:
    def __init__(self, capacity=1000, strategy=None):
        if capacity < 0:
            raise ValueError("capacity cannot be negative")

        self.capacity = capacity
        self.store = {}
        self.lock = threading.Lock()
        self.strategy = strategy if strategy else LRUStrategy()

    def get(self, key):
        with self.lock:
            if key not in self.store:
                return None
            self.strategy.on_get(key)
            return self.store[key]

    def put(self, key, value):
        with self.lock:
            if self.capacity == 0:
                return

            if key in self.store:
                self.store[key] = value
                self.strategy.on_get(key)
                return

            if len(self.store) >= self.capacity:
                evicted_key = self.strategy.evict()
                if evicted_key is not None:
                    del self.store[evicted_key]

            self.store[key] = value
            self.strategy.on_put(key)

    def delete(self, key):
        with self.lock:
            if key not in self.store:
                return False
            self.strategy.on_delete(key)
            del self.store[key]
            return True

    def clear(self):
        with self.lock:
            self.store.clear()
            self.strategy.clear()

    def set_strategy(self, strategy):
        """
        Runtime switching rebuilds the eviction metadata using existing keys.
        """
        with self.lock:
            keys = list(self.store.keys())
            self.strategy.clear()
            self.strategy = strategy
            for key in keys:
                self.strategy.on_put(key)


# ------------------ USAGE ------------------
if __name__ == "__main__":
    cache = InMemoryCache(3, LRUStrategy())

    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    cache.get("a")  # a becomes MRU
    cache.put("d", 4)  # evicts b

    print(cache.get("b"))  # None
    print(cache.get("a"))  # 1

    cache.set_strategy(LFUStrategy())
    cache.get("a")
    cache.put("e", 5)
