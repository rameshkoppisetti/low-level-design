import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from machine_coding.message_streaming.message_streaming import (
    CreateTopicRequest,
    MessageStreamingApp,
    PollRequest,
    PublishRequest,
    ValidationError,
)


class MessageStreamingTest(unittest.TestCase):
    def setUp(self):
        self.app = MessageStreamingApp()
        self.app.topic_service.create_topic(CreateTopicRequest("orders", 3))

    def test_messages_with_same_key_keep_partition_order(self):
        producer = self.app.producer_service
        consumer = self.app.consumer_service

        producer.publish(PublishRequest("orders", "m1", key="user-1"))
        producer.publish(PublishRequest("orders", "m2", key="user-1"))
        producer.publish(PublishRequest("orders", "m3", key="user-1"))

        messages = consumer.poll(PollRequest("orders", "group-1", max_messages=10))

        self.assertEqual(["m1", "m2", "m3"], [message.value for message in messages])
        self.assertEqual(1, len({message.partition_id for message in messages}))
        self.assertEqual([0, 1, 2], [message.offset for message in messages])

    def test_consumer_groups_have_independent_offsets(self):
        self.app.producer_service.publish(PublishRequest("orders", "m1", key="k1"))

        group_1_messages = self.app.consumer_service.poll(
            PollRequest("orders", "group-1", max_messages=10)
        )
        group_2_messages = self.app.consumer_service.poll(
            PollRequest("orders", "group-2", max_messages=10)
        )

        self.assertEqual(["m1"], [message.value for message in group_1_messages])
        self.assertEqual(["m1"], [message.value for message in group_2_messages])

        no_more_group_1_messages = self.app.consumer_service.poll(
            PollRequest("orders", "group-1", max_messages=10)
        )

        self.assertEqual([], no_more_group_1_messages)

    def test_round_robin_without_key(self):
        for i in range(6):
            self.app.producer_service.publish(PublishRequest("orders", f"m{i}"))

        self.assertEqual(
            {
                0: 2,
                1: 2,
                2: 2,
            },
            self.app.stats_service.get_topic_stats("orders"),
        )

    def test_blocking_poll_waits_for_message(self):
        def delayed_publish():
            time.sleep(0.05)
            self.app.producer_service.publish(PublishRequest("orders", "late-message"))

        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(delayed_publish)
            messages = self.app.consumer_service.poll(
                PollRequest("orders", "group-1", max_messages=1, timeout_seconds=1)
            )
            future.result()

        self.assertEqual(["late-message"], [message.value for message in messages])

    def test_concurrent_publishers_preserve_count(self):
        def publish(i):
            self.app.producer_service.publish(
                PublishRequest("orders", f"message-{i}", key=f"user-{i % 5}")
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(publish, i) for i in range(100)]
            for future in futures:
                future.result()

        stats = self.app.stats_service.get_topic_stats("orders")

        self.assertEqual(100, sum(stats.values()))

    def test_invalid_topic_creation_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.topic_service.create_topic(CreateTopicRequest("", 1))

        with self.assertRaises(ValidationError):
            self.app.topic_service.create_topic(CreateTopicRequest("bad", 0))


if __name__ == "__main__":
    unittest.main()
