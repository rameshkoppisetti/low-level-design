from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List


# ---------------- ENUMS ----------------

class NotificationType(Enum):
    SECURITY = "SECURITY"
    PRODUCT = "PRODUCT"
    BILLING = "BILLING"


class NotificationChannel(Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationStatus(Enum):
    UNREAD = "UNREAD"
    READ = "READ"


class Priority(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------- ENTITIES ----------------

class Notification:
    def __init__(
        self,
        notification_id,
        user_id,
        title,
        message,
        notification_type,
        priority,
        channels
    ):
        self.notification_id = notification_id
        self.user_id = user_id
        self.title = title
        self.message = message
        self.notification_type = notification_type
        self.priority = priority
        self.channels = channels

        self.status = NotificationStatus.UNREAD
        self.created_at = datetime.now()

    def mark_as_read(self):
        self.status = NotificationStatus.READ


class NotificationEvent:
    def __init__(
        self,
        user_id,
        title,
        message,
        notification_type,
        priority,
        channels
    ):
        self.user_id = user_id
        self.title = title
        self.message = message
        self.notification_type = notification_type
        self.priority = priority
        self.channels = channels


class UserPreference:
    def __init__(self, user_id, enabled_channels):
        self.user_id = user_id
        self.enabled_channels = enabled_channels


# ---------------- REPOSITORY ----------------

class NotificationRepository:

    def save(self, notification: Notification):
        print(f"Saved notification {notification.notification_id}")

    def get_user_notifications(self, user_id):
        print(f"Fetching notifications for {user_id}")

    def mark_as_read(self, notification_id):
        print(f"Marked {notification_id} as read")


class UserPreferenceRepository:

    def get_preferences(self, user_id):
        return UserPreference(
            user_id,
            [
                NotificationChannel.IN_APP,
                NotificationChannel.EMAIL
            ]
        )


# ---------------- HANDLERS ----------------

class NotificationHandler(ABC):

    @abstractmethod
    def send(self, notification: Notification):
        pass


class EmailHandler(NotificationHandler):

    def send(self, notification: Notification):
        print(f"Sending EMAIL to {notification.user_id}")


class SMSHandler(NotificationHandler):

    def send(self, notification: Notification):
        print(f"Sending SMS to {notification.user_id}")


class InAppHandler(NotificationHandler):

    def send(self, notification: Notification):
        print(f"Sending IN-APP notification to {notification.user_id}")


# ---------------- FACTORY ----------------

class NotificationHandlerFactory:

    @staticmethod
    def get_handler(channel):

        if channel == NotificationChannel.EMAIL:
            return EmailHandler()

        if channel == NotificationChannel.SMS:
            return SMSHandler()

        if channel == NotificationChannel.IN_APP:
            return InAppHandler()

        raise Exception("Invalid channel")


# ---------------- SERVICE ----------------

class NotificationService:

    def __init__(self):
        self.notification_repository = NotificationRepository()
        self.user_preference_repository = UserPreferenceRepository()

    def create_notification(self, event: NotificationEvent):

        preferences = self.user_preference_repository.get_preferences(
            event.user_id
        )

        enabled_channels = preferences.enabled_channels

        filtered_channels = []

        for channel in event.channels:
            if channel in enabled_channels:
                filtered_channels.append(channel)

        notification = Notification(
            notification_id=1,
            user_id=event.user_id,
            title=event.title,
            message=event.message,
            notification_type=event.notification_type,
            priority=event.priority,
            channels=filtered_channels
        )

        self.notification_repository.save(notification)

        for channel in filtered_channels:
            handler = NotificationHandlerFactory.get_handler(channel)
            handler.send(notification)

    def get_notifications(self, user_id):
        self.notification_repository.get_user_notifications(user_id)

    def mark_notification_as_read(self, notification_id):
        self.notification_repository.mark_as_read(notification_id)


# ---------------- CONSUMER ----------------

class NotificationConsumer:

    def __init__(self):
        self.notification_service = NotificationService()

    def consume(self, event: NotificationEvent):

        print("Consumed event from Kafka")

        self.notification_service.create_notification(event)


# ---------------- CONTROLLER ----------------

class NotificationController:

    def __init__(self):
        self.notification_service = NotificationService()

    def get_notifications(self, user_id):
        self.notification_service.get_notifications(user_id)

    def mark_as_read(self, notification_id):
        self.notification_service.mark_notification_as_read(notification_id)


# ---------------- MAIN ----------------

event = NotificationEvent(
    user_id=101,
    title="Payment Failed",
    message="Your payment has failed",
    notification_type=NotificationType.BILLING,
    priority=Priority.HIGH,
    channels=[
        NotificationChannel.EMAIL,
        NotificationChannel.SMS,
        NotificationChannel.IN_APP
    ]
)

consumer = NotificationConsumer()
consumer.consume(event)