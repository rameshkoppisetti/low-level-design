from abc import ABC, abstractmethod
from enum import Enum


# ---------------- ENUMS ----------------
class ChannelType(Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationType(Enum):
    ORDER = "ORDER"
    GENERIC = "GENERIC"


# ---------------- REQUEST ----------------
class NotificationRequest:
    def __init__(self, user, notification_type, channels, payload):
        self.user = user
        self.notification_type = notification_type
        self.channels = channels
        self.payload = payload


# ---------------- USER ----------------
class User:
    def __init__(self, email=None, phone=None):
        self.email = email
        self.phone = phone


# ---------------- HANDLERS ----------------
class NotificationHandler(ABC):
    @abstractmethod
    def send(self, user, message):
        pass


class EmailHandler(NotificationHandler):
    def send(self, user, message):
        print(f"EMAIL → {user.email}: {message}")


class SMSHandler(NotificationHandler):
    def send(self, user, message):
        print(f"SMS → {user.phone}: {message}")


# ---------------- PROCESSORS ----------------
class NotificationProcessor(ABC):
    @abstractmethod
    def process(self, request):
        pass


class OrderProcessor(NotificationProcessor):
    def process(self, request):
        return f"Order ID: {request.payload.get('orderId')}"


class GenericProcessor(NotificationProcessor):
    def process(self, request):
        return request.payload.get("message", "Default message")


# ---------------- SERVICE ----------------
class NotificationService:
    def __init__(self):
        self.handlers = {}
        self.processors = {}

    def register_handler(self, channel, handler):
        self.handlers[channel] = handler

    def register_processor(self, ntype, processor):
        self.processors[ntype] = processor

    def send(self, request):
        processor = self.processors.get(request.notification_type)
        message = processor.process(request)

        for channel in request.channels:
            handler = self.handlers.get(channel)
            if handler:
                handler.send(request.user, message)


# ---------------- DEMO ----------------
if __name__ == "__main__":
    service = NotificationService()

    # register handlers
    service.register_handler(ChannelType.EMAIL, EmailHandler())
    service.register_handler(ChannelType.SMS, SMSHandler())

    # register processors
    service.register_processor(NotificationType.ORDER, OrderProcessor())
    service.register_processor(NotificationType.GENERIC, GenericProcessor())

    user = User(email="satya@mail.com", phone="9999999999")

    req = NotificationRequest(
        user=user,
        notification_type=NotificationType.ORDER,
        channels=[ChannelType.EMAIL, ChannelType.SMS],
        payload={"orderId": "123"}
    )

    service.send(req)