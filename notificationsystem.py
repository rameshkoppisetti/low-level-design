from abc import ABC, abstractmethod
from enum import Enum
from queue import Queue
from threading import Thread, Lock
import time
import uuid


# =========================================================
# ENUMS
# =========================================================
class ChannelType(Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationType(Enum):
    ORDER = "ORDER"
    GENERIC = "GENERIC"


class DeliveryStatus(Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


# =========================================================
# USER
# =========================================================
class User:
    def __init__(
        self,
        user_id,
        email=None,
        phone=None
    ):
        self.user_id = user_id
        self.email = email
        self.phone = phone


# =========================================================
# USER PREFERENCES
# =========================================================
class UserPreference:
    def __init__(
        self,
        email_enabled=True,
        sms_enabled=True
    ):
        self.email_enabled = email_enabled
        self.sms_enabled = sms_enabled


# =========================================================
# REQUEST
# =========================================================
class NotificationRequest:
    def __init__(
        self,
        request_id,
        user,
        notification_type,
        channels,
        payload
    ):
        self.request_id = request_id
        self.user = user
        self.notification_type = notification_type
        self.channels = channels
        self.payload = payload


# =========================================================
# TEMPLATE ENGINE
# =========================================================
class TemplateEngine:

    templates = {
        NotificationType.ORDER:
            "Order {orderId} has been placed successfully.",

        NotificationType.GENERIC:
            "{message}"
    }

    @classmethod
    def render(cls, ntype, payload):

        template = cls.templates.get(
            ntype,
            "{message}"
        )

        return template.format(**payload)


# =========================================================
# RETRY POLICY
# =========================================================
class RetryPolicy:

    def __init__(
        self,
        max_retries=3,
        backoff=2
    ):
        self.max_retries = max_retries
        self.backoff = backoff


# =========================================================
# PROVIDERS
# =========================================================
class EmailProvider(ABC):

    @abstractmethod
    def send_email(self, user, message):
        pass


class SendGridProvider(EmailProvider):

    def send_email(self, user, message):

        print(
            f"[SendGrid] EMAIL -> "
            f"{user.email}: {message}"
        )


class SMSProvider(ABC):

    @abstractmethod
    def send_sms(self, user, message):
        pass


class TwilioProvider(SMSProvider):

    def send_sms(self, user, message):

        print(
            f"[Twilio] SMS -> "
            f"{user.phone}: {message}"
        )


# =========================================================
# HANDLERS
# =========================================================
class NotificationHandler(ABC):

    @abstractmethod
    def send(self, user, message):
        pass


class EmailHandler(NotificationHandler):

    def __init__(self, provider):
        self.provider = provider

    def send(self, user, message):
        self.provider.send_email(user, message)


class SMSHandler(NotificationHandler):

    def __init__(self, provider):
        self.provider = provider

    def send(self, user, message):
        self.provider.send_sms(user, message)


# =========================================================
# NOTIFICATION ENTITY (BUSINESS ENTITY)
# =========================================================
class Notification:

    def __init__(
        self,
        request,
        message
    ):

        self.id = str(uuid.uuid4())

        self.request_id = request.request_id

        self.user = request.user

        self.notification_type = (
            request.notification_type
        )

        self.message = message

        self.created_at = time.time()


# =========================================================
# DELIVERY TASK (CHANNEL DELIVERY)
# =========================================================
class DeliveryTask:

    def __init__(
        self,
        notification,
        channel
    ):

        self.id = str(uuid.uuid4())

        self.notification = notification

        self.channel = channel

        self.status = DeliveryStatus.PENDING

        self.retry_count = 0


# =========================================================
# NOTIFICATION SERVICE
# =========================================================
class NotificationService:

    def __init__(self):

        self.handlers = {}

        self.preferences = {}

        self.processed_requests = set()

        self.retry_policy = RetryPolicy()

        self.lock = Lock()

        # =================================================
        # PER CHANNEL QUEUES
        # =================================================
        self.channel_queues = {
            ChannelType.EMAIL: Queue(),
            ChannelType.SMS: Queue()
        }

        # =================================================
        # START WORKERS
        # =================================================
        self.workers = []

        for channel in self.channel_queues:

            worker = Thread(
                target=self.start_worker,
                args=(channel,),
                daemon=True
            )

            worker.start()

            self.workers.append(worker)

    # =====================================================
    # REGISTER HANDLER
    # =====================================================
    def register_handler(
        self,
        channel,
        handler
    ):
        self.handlers[channel] = handler

    # =====================================================
    # REGISTER PREFERENCES
    # =====================================================
    def register_preference(
        self,
        user_id,
        preference
    ):
        self.preferences[user_id] = preference

    # =====================================================
    # SEND
    # =====================================================
    def send(self, request):

        # -------------------------------------------------
        # IDEMPOTENCY
        # -------------------------------------------------
        with self.lock:

            if request.request_id in self.processed_requests:

                print("Duplicate request ignored")

                return

            self.processed_requests.add(
                request.request_id
            )

        # -------------------------------------------------
        # TEMPLATE RENDERING
        # -------------------------------------------------
        message = TemplateEngine.render(
            request.notification_type,
            request.payload
        )

        # -------------------------------------------------
        # CREATE SINGLE NOTIFICATION ENTITY
        # -------------------------------------------------
        notification = Notification(
            request,
            message
        )

        # -------------------------------------------------
        # CREATE DELIVERY TASKS
        # -------------------------------------------------
        for channel in request.channels:

            delivery_task = DeliveryTask(
                notification,
                channel
            )

            self.channel_queues[channel].put(
                delivery_task
            )

    # =====================================================
    # WORKER
    # =====================================================
    def start_worker(
        self,
        channel
    ):

        queue = self.channel_queues[channel]

        while True:

            delivery_task = queue.get()

            try:

                self.process(delivery_task)

            except Exception as e:

                print(
                    f"Unexpected worker error: {e}"
                )

            finally:
                queue.task_done()

    # =====================================================
    # PROCESS
    # =====================================================
    def process(
        self,
        delivery_task
    ):

        notification = delivery_task.notification

        user = notification.user

        message = notification.message

        channel = delivery_task.channel

        # -------------------------------------------------
        # PREFERENCE CHECK
        # -------------------------------------------------
        pref = self.preferences.get(user.user_id)

        if (
            channel == ChannelType.EMAIL
            and not pref.email_enabled
        ):

            print("Email disabled")

            return

        if (
            channel == ChannelType.SMS
            and not pref.sms_enabled
        ):

            print("SMS disabled")

            return

        handler = self.handlers.get(channel)

        # -------------------------------------------------
        # RETRY LOGIC
        # -------------------------------------------------
        while (
            delivery_task.retry_count <
            self.retry_policy.max_retries
        ):

            try:

                handler.send(user, message)

                delivery_task.status = (
                    DeliveryStatus.SENT
                )

                print(
                    f"Notification SENT "
                    f"[{channel.value}]"
                )

                return

            except Exception:

                delivery_task.retry_count += 1

                delivery_task.status = (
                    DeliveryStatus.RETRYING
                )

                print(
                    f"Retry "
                    f"{delivery_task.retry_count} "
                    f"for {channel.value}"
                )

                time.sleep(
                    self.retry_policy.backoff **
                    delivery_task.retry_count
                )

        # -------------------------------------------------
        # FAILED
        # -------------------------------------------------
        delivery_task.status = DeliveryStatus.FAILED

        print(
            f"Notification FAILED "
            f"[{channel.value}]"
        )


# =========================================================
# DEMO
# =========================================================
if __name__ == "__main__":

    service = NotificationService()

    # =====================================================
    # REGISTER HANDLERS
    # =====================================================
    service.register_handler(
        ChannelType.EMAIL,
        EmailHandler(
            SendGridProvider()
        )
    )

    service.register_handler(
        ChannelType.SMS,
        SMSHandler(
            TwilioProvider()
        )
    )

    # =====================================================
    # USER
    # =====================================================
    user = User(
        user_id="u1",
        email="satya@mail.com",
        phone="9999999999"
    )

    # =====================================================
    # USER PREFERENCES
    # =====================================================
    service.register_preference(
        "u1",
        UserPreference(
            email_enabled=True,
            sms_enabled=True
        )
    )

    # =====================================================
    # REQUEST
    # =====================================================
    req = NotificationRequest(
        request_id="req-1",
        user=user,
        notification_type=NotificationType.ORDER,
        channels=[
            ChannelType.EMAIL,
            ChannelType.SMS
        ],
        payload={
            "orderId": "12345"
        }
    )

    # =====================================================
    # SEND
    # =====================================================
    service.send(req)

    # duplicate request
    service.send(req)

    time.sleep(2)