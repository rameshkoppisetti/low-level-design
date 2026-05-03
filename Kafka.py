import threading
import uuid


# =========================
# MESSAGE
# =========================
class Message:
    def __init__(self, value, key=None):
        self.value = value
        self.key = key


# =========================
# PARTITION
# =========================
class Partition:
    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()

    def add_message(self, message):
        with self.lock:
            self.messages.append(message)

    def read_from(self, offset):
        with self.lock:
            return self.messages[offset:]


# =========================
# CONSUMER GROUP
# =========================
class ConsumerGroup:
    def __init__(self, group_id):
        self.group_id = group_id
        self.consumers = []
        self.partition_assignment = {}  # partition_id -> consumer
        self.lock = threading.Lock()


# =========================
# TOPIC
# =========================
class Topic:
    def __init__(self, name, num_partitions):
        self.name = name
        self.partitions = [Partition() for _ in range(num_partitions)]
        self.consumer_groups = {}
        self.count = num_partitions

    def get_partition(self, key):
        if key is None:
            return self.partitions[0]
        return self.partitions[hash(key) % self.count]

    def publish(self, key, message):
        partition = self.get_partition(key)
        partition.add_message(message)

    def subscribe(self, consumer, group_id):
        if group_id not in self.consumer_groups:
            self.consumer_groups[group_id] = ConsumerGroup(group_id)

        group = self.consumer_groups[group_id]

        with group.lock:
            if consumer not in group.consumers:
                group.consumers.append(consumer)
            self.rebalance(group)

    def rebalance(self, group):
        group.partition_assignment.clear()

        consumers = group.consumers
        n = len(consumers)

        for i in range(len(self.partitions)):
            group.partition_assignment[i] = consumers[i % n]


# =========================
# BROKER
# =========================
class Broker:
    def __init__(self):
        self.topics = {}
        self.offset_store = {}  # (group, topic, partition) -> offset

    def add_topic(self, topic, partitions):
        if topic in self.topics:
            raise Exception("Topic exists")
        self.topics[topic] = Topic(topic, partitions)

    def get_topic(self, topic):
        return self.topics[topic]

    def get_offset(self, group_id, topic, partition):
        return self.offset_store.get((group_id, topic, partition), 0)

    def commit_offset(self, group_id, topic, partition, offset):
        self.offset_store[(group_id, topic, partition)] = offset


# =========================
# CONSUMER
# =========================
class Consumer:
    def __init__(self, broker):
        self.id = str(uuid.uuid4())
        self.broker = broker
        self.group_id = None
        self.subscribed_topics = set()  # ✅ track subscriptions

    def subscribe(self, topic, group_id):
        topic_obj = self.broker.get_topic(topic)
        topic_obj.subscribe(self, group_id)

        self.group_id = group_id
        self.subscribed_topics.add(topic)

    def poll(self):
        results = []

        for topic_name in self.subscribed_topics:  # ✅ only subscribed topics
            topic = self.broker.get_topic(topic_name)
            group = topic.consumer_groups.get(self.group_id)

            if not group:
                continue

            for partition_id, consumer in group.partition_assignment.items():
                if consumer != self:
                    continue

                partition = topic.partitions[partition_id]

                offset = self.broker.get_offset(
                    self.group_id, topic_name, partition_id
                )

                messages = partition.read_from(offset)

                if messages:
                    results.extend(messages)

                    new_offset = offset + len(messages)
                    self.broker.commit_offset(
                        self.group_id, topic_name, partition_id, new_offset
                    )

        return results


# =========================
# PRODUCER
# =========================
class Producer:
    def __init__(self, broker):
        self.broker = broker

    def send(self, topic, value, key=None):
        topic_obj = self.broker.get_topic(topic)
        topic_obj.publish(key, Message(value, key))


# =========================
# DRIVER
# =========================
def main():
    broker = Broker()
    broker.add_topic("orders", 3)

    producer = Producer(broker)

    for i in range(10):
        producer.send("orders", f"order-{i}", key="user1")

    c1 = Consumer(broker)
    c2 = Consumer(broker)

    c1.subscribe("orders", "G1")
    c2.subscribe("orders", "G1")

    print("C1:", [m.value for m in c1.poll()])
    print("C2:", [m.value for m in c2.poll()])


if __name__ == "__main__":
    main()