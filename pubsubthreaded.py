import threading
import queue
import time
import uuid
from collections import defaultdict


# ================= EVENT =================
class Event:
    def __init__(self, event_id, event_type, user_id, message):
        self.id = event_id
        self.type = event_type
        self.user_id = user_id
        self.message = message


# ================= SUBSCRIBER =================
class Subscriber:
    def notify(self, event: Event):
        raise NotImplementedError


# ================= CHANNELS =================
class EmailSubscriber(Subscriber):
    def notify(self, event):
        print(f"[EMAIL] to {event.user_id}: {event.message}")


class SMSSubscriber(Subscriber):
    def notify(self, event):
        print(f"[SMS] to {event.user_id}: {event.message}")


class PushSubscriber(Subscriber):
    def notify(self, event):
        print(f"[PUSH] to {event.user_id}: {event.message}")


# ================= RETRY =================
class RetryService:
    MAX_RETRIES = 3

    @staticmethod
    def retry(event, subscriber):
        for i in range(1, RetryService.MAX_RETRIES + 1):
            try:
                time.sleep(i)  # backoff
                subscriber.notify(event)
                return
            except Exception:
                pass

        DeadLetterQueue.add(event)


# ================= DLQ =================
class DeadLetterQueue:
    failed_events = []

    @classmethod
    def add(cls, event):
        cls.failed_events.append(event)
        print(f"[DLQ] moved event {event.id}")


# ================= WORKER =================
class ChannelWorker(threading.Thread):
    def __init__(self, channel_name, subscriber, task_queue):
        super().__init__(daemon=True)
        self.channel_name = channel_name
        self.subscriber = subscriber
        self.task_queue = task_queue

    def run(self):
        while True:
            event = self.task_queue.get()
            try:
                self.subscriber.notify(event)
            except Exception:
                RetryService.retry(event, self.subscriber)
            finally:
                self.task_queue.task_done()


# ================= EVENT BUS / ORCHESTRATOR =================
class EventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)

        # per-channel queue + worker
        self.channel_queues = {}
        self.workers = {}

    def subscribe(self, event_type, subscriber: Subscriber):
        self.subscribers[event_type].append(subscriber)

        # create queue per subscriber type (channel)
        channel = type(subscriber).__name__

        if channel not in self.channel_queues:
            q = queue.Queue()
            self.channel_queues[channel] = q

            worker = ChannelWorker(channel, subscriber, q)
            worker.start()
            self.workers[channel] = worker

    def publish(self, event: Event):
        subs = self.subscribers.get(event.type, [])
        for sub in subs:
            channel = type(sub).__name__
            self.channel_queues[channel].put(event)

    def wait_until_idle(self):
        for q in self.channel_queues.values():
            q.join()


# ================= PUBLISHER =================
class EventPublisher:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def publish(self, event: Event):
        self.event_bus.publish(event)


# ================= MAIN =================
def main():
    event_bus = EventBus()
    publisher = EventPublisher(event_bus)

    # subscribe channels
    event_bus.subscribe("ORDER_PLACED", EmailSubscriber())
    event_bus.subscribe("ORDER_PLACED", SMSSubscriber())
    event_bus.subscribe("ORDER_PLACED", PushSubscriber())

    # publish event
    event = Event(
        str(uuid.uuid4()),
        "ORDER_PLACED",
        "user123",
        "Your order is placed successfully!"
    )

    publisher.publish(event)
    event_bus.wait_until_idle()


if __name__ == "__main__":
    main()
