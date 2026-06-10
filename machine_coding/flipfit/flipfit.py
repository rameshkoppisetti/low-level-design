from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from threading import RLock, Thread
from typing import Deque, Dict, List, Optional, Set, Tuple


MAX_DAILY_BOOKINGS = 3


class BookingStatus(Enum):
    BOOKED = "BOOKED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"


class RankingType(Enum):
    TIME = "TIME"
    DISTANCE = "DISTANCE"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class BookingRejectedError(Exception):
    pass


@dataclass
class Center:
    name: str
    city: str
    location: str
    latitude: float
    longitude: float
    workout_types: Set[str] = field(default_factory=set)
    lock: RLock = field(default_factory=RLock, repr=False)


@dataclass(frozen=True)
class User:
    user_id: str
    name: str


@dataclass
class WorkoutSlot:
    slot_id: str
    center_name: str
    workout_type: str
    day: str
    start_time: int
    seats: int
    waitlist_limit: int
    booked_users: Set[str] = field(default_factory=set)
    waitlist: Deque[str] = field(default_factory=deque)
    deleted: bool = False
    lock: RLock = field(default_factory=RLock, repr=False)

    def available_seats(self) -> int:
        return self.seats - len(self.booked_users)

    def is_available(self) -> bool:
        return not self.deleted and self.available_seats() > 0


@dataclass
class Booking:
    booking_id: str
    user_id: str
    slot_id: str
    status: BookingStatus


@dataclass(frozen=True)
class SlotView:
    center_name: str
    workout_type: str
    day: str
    start_time: int
    available_seats: int
    waitlist_count: int

    def encode(self) -> str:
        return (
            f"{self.center_name}|{self.workout_type}|{self.day}|"
            f"{self.start_time}|available={self.available_seats}|"
            f"waitlist={self.waitlist_count}"
        )


class NotificationPublisher(ABC):
    @abstractmethod
    def publish(self, user_id: str, message: str) -> None:
        pass


class LogNotificationPublisher(NotificationPublisher):
    def __init__(self):
        self.messages: List[str] = []
        self._lock = RLock()

    def publish(self, user_id: str, message: str) -> None:
        encoded = f"NOTIFY|{user_id}|{message}"
        with self._lock:
            self.messages.append(encoded)
        print(encoded)

    def list_messages(self) -> List[str]:
        with self._lock:
            return list(self.messages)


class CenterRepository:
    def __init__(self):
        self.centers: Dict[str, Center] = {}
        self._lock = RLock()

    def create(self, center: Center) -> None:
        with self._lock:
            key = self._key(center.name)
            if key in self.centers:
                raise ValidationError(f"Center already exists: {center.name}")
            self.centers[key] = center

    def get(self, center_name: str) -> Center:
        with self._lock:
            center = self.centers.get(self._key(center_name))
            if not center:
                raise NotFoundError(f"Center not found: {center_name}")
            return center

    def list_all(self) -> List[Center]:
        with self._lock:
            return list(self.centers.values())

    def _key(self, center_name: str) -> str:
        return center_name.strip().lower()


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def create(self, user: User) -> None:
        with self._lock:
            if user.user_id in self.users:
                raise ValidationError(f"User already exists: {user.user_id}")
            self.users[user.user_id] = user

    def get(self, user_id: str) -> User:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise NotFoundError(f"User not found: {user_id}")
            return user


class SlotRepository:
    def __init__(self):
        self.slots: Dict[str, WorkoutSlot] = {}
        self.slot_id_by_key: Dict[Tuple[str, str, str, int], str] = {}
        self.slot_ids_by_center_day: Dict[Tuple[str, str], Set[str]] = {}
        self.slot_ids_by_workout_day: Dict[Tuple[str, str], Set[str]] = {}
        self._lock = RLock()

    def save(self, slot: WorkoutSlot) -> None:
        key = self._key(slot.center_name, slot.workout_type, slot.day, slot.start_time)
        with self._lock:
            if key in self.slot_id_by_key:
                raise ValidationError("Slot already exists")
            self.slots[slot.slot_id] = slot
            self.slot_id_by_key[key] = slot.slot_id
            self.slot_ids_by_center_day.setdefault(
                (slot.center_name.lower(), slot.day),
                set(),
            ).add(slot.slot_id)
            self.slot_ids_by_workout_day.setdefault(
                (slot.workout_type.lower(), slot.day),
                set(),
            ).add(slot.slot_id)

    def get(self, slot_id: str) -> WorkoutSlot:
        with self._lock:
            slot = self.slots.get(slot_id)
            if not slot:
                raise NotFoundError(f"Slot not found: {slot_id}")
            return slot

    def find(
        self,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
    ) -> WorkoutSlot:
        key = self._key(center_name, workout_type, day, start_time)
        with self._lock:
            slot_id = self.slot_id_by_key.get(key)
            if not slot_id:
                raise NotFoundError("Slot not found")
            return self.slots[slot_id]

    def list_by_center_day(self, center_name: str, day: str) -> List[WorkoutSlot]:
        with self._lock:
            slot_ids = self.slot_ids_by_center_day.get((center_name.lower(), day), set())
            return [self.slots[slot_id] for slot_id in slot_ids]

    def list_by_workout_day(self, workout_type: str, day: str) -> List[WorkoutSlot]:
        with self._lock:
            slot_ids = self.slot_ids_by_workout_day.get((workout_type.lower(), day), set())
            return [self.slots[slot_id] for slot_id in slot_ids]

    def _key(
        self,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
    ) -> Tuple[str, str, str, int]:
        return (
            center_name.strip().lower(),
            workout_type.strip().lower(),
            day,
            start_time,
        )


class BookingRepository:
    def __init__(self):
        self.bookings: Dict[str, Booking] = {}
        self.booking_id_by_user_slot: Dict[Tuple[str, str], str] = {}
        self.booking_ids_by_user_day: Dict[Tuple[str, str], Set[str]] = {}
        self._lock = RLock()

    def save(self, booking: Booking, day: str) -> None:
        with self._lock:
            self.bookings[booking.booking_id] = booking
            self.booking_id_by_user_slot[(booking.user_id, booking.slot_id)] = booking.booking_id
            self.booking_ids_by_user_day.setdefault((booking.user_id, day), set()).add(
                booking.booking_id
            )

    def get_by_user_slot(self, user_id: str, slot_id: str) -> Optional[Booking]:
        with self._lock:
            booking_id = self.booking_id_by_user_slot.get((user_id, slot_id))
            if not booking_id:
                return None
            return self.bookings[booking_id]

    def list_by_user_day(self, user_id: str, day: str) -> List[Booking]:
        with self._lock:
            return [
                self.bookings[booking_id]
                for booking_id in self.booking_ids_by_user_day.get((user_id, day), set())
            ]


class SlotRankingStrategy(ABC):
    @abstractmethod
    def rank(
        self,
        requested_center: Center,
        requested_start_time: int,
        centers_by_name: Dict[str, Center],
        slots: List[WorkoutSlot],
    ) -> List[WorkoutSlot]:
        pass


class TimeRankingStrategy(SlotRankingStrategy):
    def rank(
        self,
        requested_center: Center,
        requested_start_time: int,
        centers_by_name: Dict[str, Center],
        slots: List[WorkoutSlot],
    ) -> List[WorkoutSlot]:
        return sorted(
            slots,
            key=lambda slot: (
                abs(slot.start_time - requested_start_time),
                _distance(requested_center, centers_by_name[slot.center_name.lower()]),
                slot.center_name,
                slot.start_time,
            ),
        )


class DistanceRankingStrategy(SlotRankingStrategy):
    def rank(
        self,
        requested_center: Center,
        requested_start_time: int,
        centers_by_name: Dict[str, Center],
        slots: List[WorkoutSlot],
    ) -> List[WorkoutSlot]:
        return sorted(
            slots,
            key=lambda slot: (
                _distance(requested_center, centers_by_name[slot.center_name.lower()]),
                abs(slot.start_time - requested_start_time),
                slot.center_name,
                slot.start_time,
            ),
        )


class SlotRankingStrategyFactory:
    def __init__(self):
        self.strategies = {
            RankingType.TIME: TimeRankingStrategy(),
            RankingType.DISTANCE: DistanceRankingStrategy(),
        }

    def get(self, ranking_type: RankingType) -> SlotRankingStrategy:
        return self.strategies[ranking_type]


class FlipFitService:
    def __init__(
        self,
        center_repo: CenterRepository,
        user_repo: UserRepository,
        slot_repo: SlotRepository,
        booking_repo: BookingRepository,
        ranking_factory: SlotRankingStrategyFactory,
        notification_publisher: NotificationPublisher,
    ):
        self.center_repo = center_repo
        self.user_repo = user_repo
        self.slot_repo = slot_repo
        self.booking_repo = booking_repo
        self.ranking_factory = ranking_factory
        self.notification_publisher = notification_publisher
        self._id_lock = RLock()
        self._next_slot_number = 1
        self._next_booking_number = 1

    def add_center(
        self,
        name: str,
        city: str,
        location: str,
        latitude: float,
        longitude: float,
    ) -> None:
        if not name.strip() or not city.strip() or not location.strip():
            raise ValidationError("Center name, city and location are required")
        self.center_repo.create(
            Center(name.strip(), city.strip(), location.strip(), latitude, longitude)
        )

    def add_workout_type(self, center_name: str, workout_type: str) -> None:
        if not workout_type.strip():
            raise ValidationError("Workout type is required")
        center = self.center_repo.get(center_name)
        with center.lock:
            center.workout_types.add(_normalize_workout(workout_type))

    def add_slot(
        self,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
        seats: int,
        waitlist_limit: int,
    ) -> str:
        if seats <= 0 or waitlist_limit < 0:
            raise ValidationError("Seats must be positive and waitlist cannot be negative")
        center = self.center_repo.get(center_name)
        workout_type = _normalize_workout(workout_type)
        with center.lock:
            if workout_type not in center.workout_types:
                raise ValidationError("Workout type not available at center")

        slot = WorkoutSlot(
            slot_id=self._next_slot_id(),
            center_name=center.name,
            workout_type=workout_type,
            day=day,
            start_time=start_time,
            seats=seats,
            waitlist_limit=waitlist_limit,
        )
        self.slot_repo.save(slot)
        return slot.slot_id

    def delete_slot(
        self,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
    ) -> None:
        slot = self.slot_repo.find(center_name, workout_type, day, start_time)
        with slot.lock:
            slot.deleted = True

    def register_user(self, user_id: str, name: str) -> None:
        if not user_id.strip() or not name.strip():
            raise ValidationError("User id and name are required")
        self.user_repo.create(User(user_id.strip(), name.strip()))

    def view_center_availability(self, center_name: str, day: str) -> List[str]:
        self.center_repo.get(center_name)
        views = []
        for slot in self.slot_repo.list_by_center_day(center_name, day):
            with slot.lock:
                if slot.deleted:
                    continue
                views.append(
                    SlotView(
                        center_name=slot.center_name,
                        workout_type=slot.workout_type,
                        day=slot.day,
                        start_time=slot.start_time,
                        available_seats=slot.available_seats(),
                        waitlist_count=len(slot.waitlist),
                    ).encode()
                )
        return sorted(views)

    def book_slot(
        self,
        user_id: str,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
    ) -> str:
        self.user_repo.get(user_id)
        slot = self.slot_repo.find(center_name, workout_type, day, start_time)

        with slot.lock:
            if slot.deleted:
                raise BookingRejectedError("Slot is deleted")
            existing = self.booking_repo.get_by_user_slot(user_id, slot.slot_id)
            if existing and existing.status != BookingStatus.CANCELLED:
                return existing.status.value
            if not self._can_book_more(user_id, day):
                raise BookingRejectedError("User daily booking limit reached")

            if slot.available_seats() > 0:
                slot.booked_users.add(user_id)
                self.booking_repo.save(
                    Booking(self._next_booking_id(), user_id, slot.slot_id, BookingStatus.BOOKED),
                    day,
                )
                return BookingStatus.BOOKED.value

            if len(slot.waitlist) >= slot.waitlist_limit:
                raise BookingRejectedError("Slot and waitlist are full")

            slot.waitlist.append(user_id)
            self.booking_repo.save(
                Booking(self._next_booking_id(), user_id, slot.slot_id, BookingStatus.WAITLISTED),
                day,
            )
            return BookingStatus.WAITLISTED.value

    def cancel_slot(
        self,
        user_id: str,
        center_name: str,
        workout_type: str,
        day: str,
        start_time: int,
    ) -> List[str]:
        self.user_repo.get(user_id)
        slot = self.slot_repo.find(center_name, workout_type, day, start_time)
        notifications = []

        with slot.lock:
            booking = self.booking_repo.get_by_user_slot(user_id, slot.slot_id)
            if not booking or booking.status == BookingStatus.CANCELLED:
                raise NotFoundError("Active booking not found")

            booking.status = BookingStatus.CANCELLED
            if user_id in slot.booked_users:
                slot.booked_users.remove(user_id)
                message = f"Cancelled {slot.workout_type} at {slot.center_name} {slot.start_time}"
                self.notification_publisher.publish(user_id, message)
                notifications.append(message)
                promoted_message = self._promote_waitlisted_user_locked(slot)
                if promoted_message:
                    notifications.append(promoted_message)
            else:
                slot.waitlist = deque(item for item in slot.waitlist if item != user_id)
                message = f"Removed from waitlist for {slot.workout_type} at {slot.center_name}"
                self.notification_publisher.publish(user_id, message)
                notifications.append(message)

        return notifications

    def view_user_booking(self, user_id: str, day: str) -> List[str]:
        self.user_repo.get(user_id)
        rows = []
        for booking in self.booking_repo.list_by_user_day(user_id, day):
            if booking.status != BookingStatus.BOOKED:
                continue
            slot = self.slot_repo.get(booking.slot_id)
            with slot.lock:
                if not slot.deleted:
                    rows.append(
                        f"{slot.day}|{slot.center_name}|{slot.workout_type}|{slot.start_time}"
                    )
        return sorted(rows)

    def recommend_slot(
        self,
        center_name: str,
        slot_time: int,
        workout_type: str,
        user_id: str,
        day: str,
        ranking_type: RankingType,
    ) -> List[str]:
        self.user_repo.get(user_id)
        requested_center = self.center_repo.get(center_name)
        centers_by_name = {
            center.name.lower(): center
            for center in self.center_repo.list_all()
        }
        available_slots = []

        for slot in self.slot_repo.list_by_workout_day(workout_type, day):
            with slot.lock:
                if slot.deleted or slot.available_seats() <= 0:
                    continue
                if slot.center_name.lower() == center_name.lower() and slot.start_time == slot_time:
                    continue
                available_slots.append(slot)

        strategy = self.ranking_factory.get(ranking_type)
        ranked_slots = strategy.rank(
            requested_center,
            slot_time,
            centers_by_name,
            available_slots,
        )
        return [
            f"{slot.center_name}|{slot.workout_type}|{slot.day}|{slot.start_time}|available={slot.available_seats()}"
            for slot in ranked_slots[:3]
        ]

    def _promote_waitlisted_user_locked(self, slot: WorkoutSlot) -> Optional[str]:
        while slot.waitlist and slot.available_seats() > 0:
            next_user_id = slot.waitlist.popleft()
            booking = self.booking_repo.get_by_user_slot(next_user_id, slot.slot_id)
            if not booking or booking.status != BookingStatus.WAITLISTED:
                continue
            if not self._can_book_more(next_user_id, slot.day):
                booking.status = BookingStatus.CANCELLED
                continue

            booking.status = BookingStatus.BOOKED
            slot.booked_users.add(next_user_id)
            message = f"Promoted to booked for {slot.workout_type} at {slot.center_name} {slot.start_time}"
            self.notification_publisher.publish(next_user_id, message)
            return message
        return None

    def _can_book_more(self, user_id: str, day: str) -> bool:
        booked_count = sum(
            1
            for booking in self.booking_repo.list_by_user_day(user_id, day)
            if booking.status == BookingStatus.BOOKED
        )
        return booked_count < MAX_DAILY_BOOKINGS

    def _next_slot_id(self) -> str:
        with self._id_lock:
            slot_id = f"S{self._next_slot_number}"
            self._next_slot_number += 1
            return slot_id

    def _next_booking_id(self) -> str:
        with self._id_lock:
            booking_id = f"B{self._next_booking_number}"
            self._next_booking_number += 1
            return booking_id


class FlipFit:
    def __init__(self):
        self.center_repo = CenterRepository()
        self.user_repo = UserRepository()
        self.slot_repo = SlotRepository()
        self.booking_repo = BookingRepository()
        self.ranking_factory = SlotRankingStrategyFactory()
        self.notification_publisher = LogNotificationPublisher()
        self.service = FlipFitService(
            self.center_repo,
            self.user_repo,
            self.slot_repo,
            self.booking_repo,
            self.ranking_factory,
            self.notification_publisher,
        )


def _normalize_workout(workout_type: str) -> str:
    return workout_type.strip().lower()


def _distance(first: Center, second: Center) -> float:
    return sqrt(
        (first.latitude - second.latitude) ** 2
        + (first.longitude - second.longitude) ** 2
    )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(app: FlipFit) -> None:
    service = app.service
    service.add_center("Bellandur", "Bangalore", "Bellandur Main Road", 12.93, 77.68)
    service.add_center("HSR", "Bangalore", "HSR Layout", 12.91, 77.64)
    service.add_center("Indiranagar", "Bangalore", "Indiranagar", 12.97, 77.64)
    service.add_workout_type("Bellandur", "Weights")
    service.add_workout_type("Bellandur", "Yoga")
    service.add_workout_type("HSR", "Weights")
    service.add_workout_type("Indiranagar", "Weights")
    service.add_slot("Bellandur", "Weights", "MONDAY", 360, 1, 2)
    service.add_slot("Bellandur", "Yoga", "MONDAY", 420, 2, 1)
    service.add_slot("HSR", "Weights", "MONDAY", 390, 2, 1)
    service.add_slot("Indiranagar", "Weights", "MONDAY", 360, 2, 1)
    service.register_user("u1", "Anu")
    service.register_user("u2", "Bala")
    service.register_user("u3", "Charu")


def test_booking_waitlist_and_promotion() -> None:
    app = FlipFit()
    seed_data(app)
    service = app.service

    assert_equal(
        BookingStatus.BOOKED.value,
        service.book_slot("u1", "Bellandur", "Weights", "MONDAY", 360),
        "first user booked",
    )
    assert_equal(
        BookingStatus.WAITLISTED.value,
        service.book_slot("u2", "Bellandur", "Weights", "MONDAY", 360),
        "second user waitlisted",
    )
    service.cancel_slot("u1", "Bellandur", "Weights", "MONDAY", 360)
    assert_equal(
        ["MONDAY|Bellandur|weights|360"],
        service.view_user_booking("u2", "MONDAY"),
        "waitlisted user promoted",
    )


def test_daily_limit_and_recommendation() -> None:
    app = FlipFit()
    seed_data(app)
    service = app.service

    service.book_slot("u1", "Bellandur", "Weights", "MONDAY", 360)
    service.book_slot("u1", "Bellandur", "Yoga", "MONDAY", 420)
    service.book_slot("u1", "HSR", "Weights", "MONDAY", 390)

    rejected = False
    try:
        service.book_slot("u1", "Indiranagar", "Weights", "MONDAY", 360)
    except BookingRejectedError:
        rejected = True
    assert_equal(True, rejected, "daily limit enforced")

    assert_equal(
        [
            "Indiranagar|weights|MONDAY|360|available=2",
            "HSR|weights|MONDAY|390|available=1",
        ],
        service.recommend_slot(
            "Bellandur",
            360,
            "Weights",
            "u2",
            "MONDAY",
            RankingType.TIME,
        ),
        "time based recommendations",
    )


def test_availability_and_delete_slot() -> None:
    app = FlipFit()
    seed_data(app)
    service = app.service

    assert_equal(
        [
            "Bellandur|weights|MONDAY|360|available=1|waitlist=0",
            "Bellandur|yoga|MONDAY|420|available=2|waitlist=0",
        ],
        service.view_center_availability("Bellandur", "MONDAY"),
        "center availability",
    )
    service.delete_slot("Bellandur", "Yoga", "MONDAY", 420)
    assert_equal(
        ["Bellandur|weights|MONDAY|360|available=1|waitlist=0"],
        service.view_center_availability("Bellandur", "MONDAY"),
        "deleted slot hidden",
    )


def test_concurrent_booking_only_one_seat() -> None:
    app = FlipFit()
    seed_data(app)
    service = app.service
    results = []

    def book(user_id: str) -> None:
        results.append(service.book_slot(user_id, "Bellandur", "Weights", "MONDAY", 360))

    first = Thread(target=book, args=("u1",))
    second = Thread(target=book, args=("u2",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert_equal(
        [BookingStatus.BOOKED.value, BookingStatus.WAITLISTED.value],
        sorted(results),
        "one booked and one waitlisted concurrently",
    )


def run_tests() -> None:
    test_booking_waitlist_and_promotion()
    test_daily_limit_and_recommendation()
    test_availability_and_delete_slot()
    test_concurrent_booking_only_one_seat()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
