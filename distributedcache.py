from abc import ABC, abstractmethod
from collections import defaultdict
import threading


# ------------------ NODE ------------------
class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.freq = 1
        self.prev = None
        self.next = None


# ------------------ DLL ------------------
class DoublyLinkedList:
    def __init__(self):
        self.head = Node(None, None)
        self.tail = Node(None, None)
        self.head.next = self.tail
        self.tail.prev = self.head

    def add_front(self, node):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def remove(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def remove_last(self):
        if self.tail.prev == self.head:
            return None
        node = self.tail.prev
        self.remove(node)
        return node

    def is_empty(self):
        return self.head.next == self.tail


# ------------------ STRATEGY INTERFACE ------------------
class EvictionStrategy(ABC):

    @abstractmethod
    def on_get(self, node): pass

    @abstractmethod
    def on_put(self, node): pass

    @abstractmethod
    def on_delete(self, node): pass

    @abstractmethod
    def evict(self): pass

    @abstractmethod
    def clear(self): pass


# ------------------ LRU ------------------
class LRUStrategy(EvictionStrategy):
    def __init__(self):
        self.dll = DoublyLinkedList()

    def on_get(self, node):
        self.dll.remove(node)
        self.dll.add_front(node)

    def on_put(self, node):
        self.dll.add_front(node)

    def on_delete(self, node):
        self.dll.remove(node)

    def evict(self):
        return self.dll.remove_last()

    def clear(self):
        self.dll = DoublyLinkedList()


# ------------------ FIFO ------------------
class FIFOStrategy(EvictionStrategy):
    def __init__(self):
        self.dll = DoublyLinkedList()

    def on_get(self, node):
        pass  # no change

    def on_put(self, node):
        self.dll.add_front(node)

    def on_delete(self, node):
        self.dll.remove(node)

    def evict(self):
        return self.dll.remove_last()

    def clear(self):
        self.dll = DoublyLinkedList()


# ------------------ LFU ------------------
class LFUStrategy(EvictionStrategy):
    def __init__(self):
        self.freq_map = defaultdict(DoublyLinkedList)
        self.min_freq = 1

    def _update(self, node):
        freq = node.freq
        self.freq_map[freq].remove(node)

        if self.freq_map[freq].is_empty() and freq == self.min_freq:
            self.min_freq += 1

        node.freq += 1
        self.freq_map[node.freq].add_front(node)

    def on_get(self, node):
        self._update(node)

    def on_put(self, node):
        self.freq_map[1].add_front(node)
        self.min_freq = 1

    def on_delete(self, node):
        self.freq_map[node.freq].remove(node)

    def evict(self):
        dll = self.freq_map[self.min_freq]
        return dll.remove_last()

    def clear(self):
        self.freq_map.clear()
        self.min_freq = 1


# ------------------ CACHE ------------------
class InMemoryCache:
    def __init__(self, capacity=1000, strategy=None):
        self.capacity = capacity
        self.map = {}
        self.lock = threading.Lock()
        self.strategy = strategy if strategy else LRUStrategy()

    def get(self, key):
        with self.lock:
            if key not in self.map:
                return None
            node = self.map[key]
            self.strategy.on_get(node)
            return node.value

    def put(self, key, value):
        with self.lock:
            if key in self.map:
                node = self.map[key]
                node.value = value
                self.strategy.on_get(node)
                return

            if len(self.map) >= self.capacity:
                evicted = self.strategy.evict()
                if evicted:
                    del self.map[evicted.key]

            node = Node(key, value)
            self.map[key] = node
            self.strategy.on_put(node)

    def delete(self, key):
        with self.lock:
            if key not in self.map:
                return False
            node = self.map[key]
            self.strategy.on_delete(node)
            del self.map[key]
            return True

    def clear(self):
        with self.lock:
            self.map.clear()
            self.strategy.clear()

    def set_strategy(self, strategy):
        """
        Runtime switching (rebuild structure)
        """
        with self.lock:
            nodes = list(self.map.values())
            self.strategy.clear()
            self.strategy = strategy
            for node in nodes:
                node.freq = 1  # reset for LFU sanity
                self.strategy.on_put(node)


# ------------------ USAGE ------------------
if __name__ == "__main__":
    cache = InMemoryCache(3, LRUStrategy())

    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    cache.get("a")  # a becomes MRU
    cache.put("d", 4)  # evicts b (LRU)

    print(cache.get("b"))  # None
    print(cache.get("a"))  # 1

    # Switch to LFU
    cache.set_strategy(LFUStrategy())
    cache.put("e", 5)