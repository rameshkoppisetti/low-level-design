import enum
import threading
import queue
import time
from abc import ABC, abstractmethod


# ---------------- ENUMS ----------------
class ChannelType(enum.Enum):
    SMS = 'SMS'
    MAIL = 'MAIL'
    WHATSAPP = 'WHATSAPP'


class RequestType(enum.Enum):
    PRICE_UPDATED = 'PRICE_UPDATED'
    ORDER_CONFIRMED = 'ORDER_CONFIRMED'


# ---------------- USER ----------------
class User:
    def __init__(self, name, email, phone):
        self.name = name
        self.email = email
        self.phone = phone


# ---------------- REQUEST ----------------
class NotificationRequest:
    def __init__(self, id, requestType, user, channels, payload):
        self.id = id
        self.requestType = requestType
        self.user = user
        self.channels = channels
        self.payload = payload


# ---------------- HANDLERS ----------------
class Handler(ABC):
    @abstractmethod
    def send(self, user, message):
        pass


class EmailHandler(Handler):
    def send(self, user, message):
        print(f"[EMAIL] to {user.email}: {message}")


class SMSHandler(Handler):
    def send(self, user, message):
        print(f"[SMS] to {user.phone}: {message}")


class WhatsAppHandler(Handler):
    def send(self, user, message):
        print(f"[WHATSAPP] to {user.phone}: {message}")


# ---------------- PROCESSORS ----------------
class Processor(ABC):
    @abstractmethod
    def process(self, request):
        pass


class PriceProcessor(Processor):
    def process(self, request):
        return f"Price updated: {request.payload}"


class OrderProcessor(Processor):
    def process(self, request):
        return f"Order confirmed for {request.user.name}"


# ---------------- WORKER ----------------
class ChannelWorker(threading.Thread):
    def __init__(self, channel_type, handler, task_queue):
        super().__init__(daemon=True)
        self.channel_type = channel_type
        self.handler = handler
        self.task_queue = task_queue

    def run(self):
        while True:
            user, message = self.task_queue.get()
            try:
                self.handler.send(user, message)
            except Exception as e:
                print(f"[ERROR] {self.channel_type}: {e}")
            finally:
                self.task_queue.task_done()


# ---------------- SERVICE ----------------
class NotificationService:
    def __init__(self):
        self.handlers = {}
        self.processors = {}

        self.queues = {}        # channel → queue
        self.workers = {}       # channel → worker

    def add_handler(self, channelType, handler):
        self.handlers[channelType] = handler

        # create queue per channel
        q = queue.Queue()
        self.queues[channelType] = q

        # start worker
        worker = ChannelWorker(channelType, handler, q)
        worker.start()
        self.workers[channelType] = worker

    def add_processor(self, requestType, processor):
        self.processors[requestType] = processor

    def send(self, request):
        processor = self.processors.get(request.requestType)
        if not processor:
            raise Exception("Processor not found")

        message = processor.process(request)

        for channel in request.channels:
            if channel in self.queues:
                self.queues[channel].put((request.user, message))


# ---------------- DEMO ----------------
def main():
    service = NotificationService()

    # Register handlers
    service.add_handler(ChannelType.SMS, SMSHandler())
    service.add_handler(ChannelType.MAIL, EmailHandler())
    service.add_handler(ChannelType.WHATSAPP, WhatsAppHandler())

    # Register processors
    service.add_processor(RequestType.PRICE_UPDATED, PriceProcessor())
    service.add_processor(RequestType.ORDER_CONFIRMED, OrderProcessor())

    user = User("Satya", "satya@mail.com", "+919999999")

    # simulate multiple threads sending requests
    def send_requests(i):
        req = NotificationRequest(
            i,
            RequestType.PRICE_UPDATED,
            user,
            [ChannelType.MAIL, ChannelType.SMS],
            payload=f"item-{i}"
        )
        service.send(req)

    threads = []
    for i in range(5):
        t = threading.Thread(target=send_requests, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # wait for queues to finish
    time.sleep(2)


if __name__ == "__main__":
    main()