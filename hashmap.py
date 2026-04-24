import threading


class Node:
    """
    Node for linked list (used in chaining for collision handling)
    """
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.next = None


class HashMap:
    """
    Thread-safe HashMap using:
    - Separate chaining (linked list per bucket)
    - Rehashing when load factor exceeded
    - Global lock (RLock) for simplicity
    """
    def __init__(self, capacity=8):
        self.capacity = capacity                  # number of buckets
        self.buckets = [None] * capacity          # array of linked lists
        self.size = 0                             # number of key-value pairs
        self.loadfactor = 0.75                    # resize threshold
        self.lock = threading.RLock()             # reentrant lock (important!)

    def hash_key(self, key):
        """
        Compute bucket index using built-in hash
        """
        return hash(key) % self.capacity

    def put(self, key, value):
        """
        Insert or update key-value pair
        Time: O(1) avg
        """
        with self.lock:   # ensure thread safety
            index = self.hash_key(key)
            head = self.buckets[index]

            # Check if key already exists → update
            cur = head
            while cur:
                if cur.key == key:
                    cur.value = value
                    return
                cur = cur.next

            # Insert new node at head (O(1))
            new_node = Node(key, value)
            new_node.next = head
            self.buckets[index] = new_node
            self.size += 1

            # Check load factor → trigger resize
            if self.size / self.capacity > self.loadfactor:
                self.rebalance()

    def get(self, key):
        """
        Retrieve value for a key
        Time: O(1) avg
        """
        with self.lock:
            index = self.hash_key(key)
            cur = self.buckets[index]

            # Traverse linked list
            while cur:
                if cur.key == key:
                    return cur.value
                cur = cur.next

            return None  # key not found

    def rebalance(self):
        """
        Double capacity and rehash all elements
        Important: must reinsert using new hash
        """
        old_buckets = self.buckets

        # Double capacity
        self.capacity *= 2
        self.buckets = [None] * self.capacity
        self.size = 0  # will be rebuilt

        # Rehash all existing elements
        for bucket in old_buckets:
            cur = bucket
            while cur:
                self.put(cur.key, cur.value)  # reinsert with new capacity
                cur = cur.next


# ------------------ TEST ------------------

if __name__ == "__main__":
    hashmap = HashMap()

    hashmap.put("satya", "hi")
    hashmap.put("hello", "world")
    hashmap.put("satya", "updated")  # update existing key

    print(hashmap.get("satya"))   # updated
    print(hashmap.get("hello"))   # world
    print(hashmap.get("none"))    # None