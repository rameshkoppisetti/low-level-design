class Node:
    def __init__(self, item_id):
        self.item_id = item_id
        self.prev = None
        self.next = None

class LRUCache:

    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = {}  # item_id -> Node

        # Dummy head and tail
        self.head = Node(0)
        self.tail = Node(0)
        self.head.next = self.tail
        self.tail.prev = self.head

    # -------------------------
    # Internal Helpers
    # -------------------------

    def _add_to_front(self, node):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def _remove_node(self, node):
        prev_node = node.prev
        next_node = node.next
        prev_node.next = next_node
        next_node.prev = prev_node

    def _move_to_front(self, node):
        self._remove_node(node)
        self._add_to_front(node)

    def _remove_lru(self):
        lru = self.tail.prev
        self._remove_node(lru)
        del self.cache[lru.item_id]

    # -------------------------
    # Public API
    # -------------------------

    def view_item(self, item_id):

        if item_id in self.cache:
            node = self.cache[item_id]
            self._move_to_front(node)
        else:
            node = Node(item_id)
            self.cache[item_id] = node
            self._add_to_front(node)

            if len(self.cache) > self.capacity:
                self._remove_lru()

    def get_recent_items(self):
        result = []
        current = self.head.next
        while current != self.tail:
            result.append(current.item_id)
            current = current.next
        return result

class RecentlyViewedService:

    def __init__(self, limit):
        self.limit = limit
        self.user_data = {}  # user_id -> LRUCache

    def view_item(self, user_id, item_id):

        if user_id not in self.user_data:
            self.user_data[user_id] = LRUCache(self.limit)

        self.user_data[user_id].view_item(item_id)

    def get_recent_items(self, user_id):

        if user_id not in self.user_data:
            return []

        return self.user_data[user_id].get_recent_items()

def main():
    service = RecentlyViewedService(limit=3)

    service.view_item("U1", "ItemA")
    service.view_item("U1", "ItemB")
    service.view_item("U1", "ItemC")
    
    service.view_item("U2", "Item1")
    service.view_item("U2", "Item2")
    service.view_item("U2", "Item3")

    print(service.get_recent_items("U1"))
    # ['ItemC', 'ItemB', 'ItemA']

    service.view_item("U1", "ItemD")
    print(service.get_recent_items("U1"))
    # ['ItemD', 'ItemC', 'ItemB']  (ItemA removed)

    service.view_item("U1", "ItemB")
    print(service.get_recent_items("U1"))
    # ['ItemB', 'ItemD', 'ItemC']
    print(service.get_recent_items("U2"))


if __name__ == "__main__":
    main()