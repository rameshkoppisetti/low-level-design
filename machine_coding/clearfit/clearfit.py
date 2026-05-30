from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional, Set, Tuple
import uuid


DEFAULT_DAY = "TODAY"


class BookingStatus(Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class ClearFitError(Exception):
    pass


class EntityNotFoundError(ClearFitError):
    pass


class ValidationError(ClearFitError):
    pass


class SlotUnavailableError(ClearFitError):
    pass


@dataclass(frozen=True)
class TimeRange:
    start_time: int
    end_time: int

    def __post_init__(self):
        if self.start_time < 0 or self.end_time > 24 or self.start_time >= self.end_time:
            raise ValidationError("Invalid time range")

    def contains(self, other: "TimeRange") -> bool:
        return self.start_time <= other.start_time and other.end_time <= self.end_time

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start_time < other.end_time and other.start_time < self.end_time


@dataclass(frozen=True)
class AddWorkoutRequest:
    center_name: str
    workout_type: str
    start_time: int
    end_time: int
    seats: int
    day: str = DEFAULT_DAY


@dataclass(frozen=True)
class SessionRequest:
    user_name: str
    center_name: str
    workout_type: str
    start_time: int
    end_time: int
    day: str = DEFAULT_DAY


@dataclass(frozen=True)
class SlotView:
    center_name: str
    workout_type: str
    start_time: int
    end_time: int
    seats_available: int

    def __str__(self) -> str:
        return (
            f"{self.center_name}, {self.workout_type}, "
            f"{self.start_time}, {self.end_time}, {self.seats_available}"
        )


@dataclass
class Center:
    name: str
    timings: List[TimeRange] = field(default_factory=list)
    activities: Set[str] = field(default_factory=set)


@dataclass
class User:
    name: str


@dataclass
class WorkoutSlot:
    slot_id: str
    center_name: str
    workout_type: str
    start_time: int
    end_time: int
    total_seats: int
    day: str = DEFAULT_DAY
    booked_users: Set[str] = field(default_factory=set)
    lock: RLock = field(default_factory=RLock, repr=False)

    def available_seats(self) -> int:
        return self.total_seats - len(self.booked_users)

    def key(self) -> Tuple[str, str, str, int, int]:
        return (
            self.day,
            self.center_name.lower(),
            self.workout_type.lower(),
            self.start_time,
            self.end_time,
        )

    def time_range(self) -> TimeRange:
        return TimeRange(self.start_time, self.end_time)


@dataclass
class Booking:
    booking_id: str
    user_name: str
    slot_id: str
    status: BookingStatus = BookingStatus.BOOKED


class CenterRepository:
    def __init__(self):
        self.centers: Dict[str, Center] = {}
        self._lock = RLock()

    def add_center(self, center_name: str) -> None:
        center_key = self._key(center_name)
        with self._lock:
            if center_key in self.centers:
                raise ValidationError(f"Center already exists: {center_name}")
            self.centers[center_key] = Center(center_name)

    def add_timings(self, center_name: str, timings: List[TimeRange]) -> None:
        with self._lock:
            center = self._get_or_raise(center_name)
            center.timings = list(timings)

    def add_activities(self, center_name: str, activities: List[str]) -> None:
        with self._lock:
            center = self._get_or_raise(center_name)
            center.activities.update(self._normalize_activity(activity) for activity in activities)

    def get(self, center_name: str) -> Center:
        with self._lock:
            return self._get_or_raise(center_name)

    def _get_or_raise(self, center_name: str) -> Center:
        center = self.centers.get(self._key(center_name))
        if not center:
            raise EntityNotFoundError(f"Center not found: {center_name}")
        return center

    def _key(self, center_name: str) -> str:
        return center_name.strip().lower()

    def _normalize_activity(self, activity: str) -> str:
        return activity.strip().lower()


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def register(self, user_name: str) -> None:
        key = self._key(user_name)
        with self._lock:
            if key in self.users:
                raise ValidationError(f"User already registered: {user_name}")
            self.users[key] = User(user_name.strip())

    def exists(self, user_name: str) -> bool:
        with self._lock:
            return self._key(user_name) in self.users

    def get_or_raise(self, user_name: str) -> User:
        with self._lock:
            user = self.users.get(self._key(user_name))
            if not user:
                raise EntityNotFoundError(f"User not registered: {user_name}")
            return user

    def _key(self, user_name: str) -> str:
        return user_name.strip().lower()


class SlotRepository:
    def __init__(self):
        self.slots_by_id: Dict[str, WorkoutSlot] = {}
        self.slots_by_key: Dict[Tuple[str, str, str, int, int], str] = {}
        self.slot_ids_by_workout: Dict[Tuple[str, str], Set[str]] = {}
        self.slot_ids_by_center_day: Dict[Tuple[str, str], Set[str]] = {}
        self._lock = RLock()

    def save(self, slot: WorkoutSlot) -> None:
        with self._lock:
            if slot.key() in self.slots_by_key:
                raise ValidationError("Workout slot already exists")

            for existing in self._center_day_slots(slot.center_name, slot.day):
                if existing.time_range().overlaps(slot.time_range()):
                    raise ValidationError("Center already has a workout in this time range")

            self.slots_by_id[slot.slot_id] = slot
            self.slots_by_key[slot.key()] = slot.slot_id

            workout_index_key = (slot.day, slot.workout_type.lower())
            self.slot_ids_by_workout.setdefault(workout_index_key, set()).add(slot.slot_id)

            center_day_key = (slot.day, slot.center_name.lower())
            self.slot_ids_by_center_day.setdefault(center_day_key, set()).add(slot.slot_id)

    def find_slot(
        self,
        center_name: str,
        workout_type: str,
        start_time: int,
        end_time: int,
        day: str = DEFAULT_DAY,
    ) -> WorkoutSlot:
        key = (
            day,
            center_name.strip().lower(),
            workout_type.strip().lower(),
            start_time,
            end_time,
        )
        with self._lock:
            slot_id = self.slots_by_key.get(key)
            if not slot_id:
                raise EntityNotFoundError("Workout slot not found")
            return self.slots_by_id[slot_id]

    def list_by_workout(self, workout_type: str, day: str = DEFAULT_DAY) -> List[WorkoutSlot]:
        index_key = (day, workout_type.strip().lower())
        with self._lock:
            return [
                self.slots_by_id[slot_id]
                for slot_id in self.slot_ids_by_workout.get(index_key, set())
            ]

    def _center_day_slots(self, center_name: str, day: str) -> List[WorkoutSlot]:
        center_day_key = (day, center_name.strip().lower())
        return [
            self.slots_by_id[slot_id]
            for slot_id in self.slot_ids_by_center_day.get(center_day_key, set())
        ]


class BookingRepository:
    def __init__(self):
        self.bookings_by_id: Dict[str, Booking] = {}
        self.active_booking_by_user_slot: Dict[Tuple[str, str], str] = {}
        self._lock = RLock()

    def create_booking(self, user_name: str, slot_id: str) -> Booking:
        with self._lock:
            key = self._user_slot_key(user_name, slot_id)
            if key in self.active_booking_by_user_slot:
                raise ValidationError("User already booked this slot")

            booking = Booking(
                booking_id=f"BKG-{uuid.uuid4().hex[:8].upper()}",
                user_name=user_name,
                slot_id=slot_id,
            )
            self.bookings_by_id[booking.booking_id] = booking
            self.active_booking_by_user_slot[key] = booking.booking_id
            return booking

    def cancel_booking(self, user_name: str, slot_id: str) -> Booking:
        with self._lock:
            key = self._user_slot_key(user_name, slot_id)
            booking_id = self.active_booking_by_user_slot.get(key)
            if not booking_id:
                raise EntityNotFoundError("Active booking not found")

            booking = self.bookings_by_id[booking_id]
            booking.status = BookingStatus.CANCELLED
            del self.active_booking_by_user_slot[key]
            return booking

    def _user_slot_key(self, user_name: str, slot_id: str) -> Tuple[str, str]:
        return user_name.strip().lower(), slot_id


class CenterService:
    def __init__(self, center_repo: CenterRepository):
        self.center_repo = center_repo

    def add_centre(self, center_name: str) -> None:
        if not center_name.strip():
            raise ValidationError("Center name cannot be empty")
        self.center_repo.add_center(center_name)

    def add_centre_timings(self, center_name: str, timings: List[Tuple[int, int]]) -> None:
        self.center_repo.add_timings(
            center_name,
            [TimeRange(start, end) for start, end in timings],
        )

    def add_centre_activities(self, center_name: str, activities: List[str]) -> None:
        if not activities:
            raise ValidationError("At least one activity is required")
        self.center_repo.add_activities(center_name, activities)


class WorkoutAdminService:
    def __init__(self, center_repo: CenterRepository, slot_repo: SlotRepository):
        self.center_repo = center_repo
        self.slot_repo = slot_repo

    def add_workout(self, request: AddWorkoutRequest) -> str:
        if request.seats <= 0:
            raise ValidationError("Seats must be positive")

        center = self.center_repo.get(request.center_name)
        workout_type = request.workout_type.strip()
        workout_key = workout_type.lower()
        time_range = TimeRange(request.start_time, request.end_time)

        if workout_key not in center.activities:
            raise ValidationError(f"Workout not supported by center: {request.workout_type}")

        if not any(center_timing.contains(time_range) for center_timing in center.timings):
            raise ValidationError("Workout slot is outside center timings")

        slot = WorkoutSlot(
            slot_id=f"SLOT-{uuid.uuid4().hex[:8].upper()}",
            center_name=center.name,
            workout_type=workout_type,
            start_time=request.start_time,
            end_time=request.end_time,
            total_seats=request.seats,
            day=request.day,
        )
        self.slot_repo.save(slot)
        return slot.slot_id


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def register(self, user_name: str) -> None:
        if not user_name.strip():
            raise ValidationError("User name cannot be empty")
        self.user_repo.register(user_name)


class BookingService:
    def __init__(
        self,
        user_repo: UserRepository,
        slot_repo: SlotRepository,
        booking_repo: BookingRepository,
    ):
        self.user_repo = user_repo
        self.slot_repo = slot_repo
        self.booking_repo = booking_repo

    def book_session(self, request: SessionRequest) -> Booking:
        self.user_repo.get_or_raise(request.user_name)
        slot = self._find_slot(request)
        user_key = request.user_name.strip().lower()

        with slot.lock:
            if user_key in slot.booked_users:
                raise ValidationError("User already booked this slot")

            if slot.available_seats() <= 0:
                raise SlotUnavailableError("No seats available")

            booking = self.booking_repo.create_booking(request.user_name, slot.slot_id)
            slot.booked_users.add(user_key)
            return booking

    def cancel_session(self, request: SessionRequest) -> Booking:
        self.user_repo.get_or_raise(request.user_name)
        slot = self._find_slot(request)
        user_key = request.user_name.strip().lower()

        with slot.lock:
            booking = self.booking_repo.cancel_booking(request.user_name, slot.slot_id)
            slot.booked_users.remove(user_key)
            return booking

    def _find_slot(self, request: SessionRequest) -> WorkoutSlot:
        return self.slot_repo.find_slot(
            request.center_name,
            request.workout_type,
            request.start_time,
            request.end_time,
            request.day,
        )


class AvailabilityService:
    def __init__(self, slot_repo: SlotRepository):
        self.slot_repo = slot_repo

    def view_workout_availability(
        self,
        workout_type: str,
        center_name: Optional[str] = None,
        day: str = DEFAULT_DAY,
    ) -> List[SlotView]:
        slots = self.slot_repo.list_by_workout(workout_type, day)

        if center_name:
            center_key = center_name.strip().lower()
            slots = [
                slot for slot in slots
                if slot.center_name.lower() == center_key
            ]

        views = [self._to_view(slot) for slot in slots]

        if center_name:
            return sorted(
                views,
                key=lambda view: (
                    view.seats_available,
                    view.start_time,
                    view.center_name,
                ),
            )

        return sorted(
            views,
            key=lambda view: (
                view.start_time,
                view.center_name,
                view.seats_available,
            ),
        )

    def _to_view(self, slot: WorkoutSlot) -> SlotView:
        with slot.lock:
            return SlotView(
                center_name=slot.center_name,
                workout_type=slot.workout_type,
                start_time=slot.start_time,
                end_time=slot.end_time,
                seats_available=slot.available_seats(),
            )


class ClearFitApp:
    def __init__(self):
        self.center_repo = CenterRepository()
        self.user_repo = UserRepository()
        self.slot_repo = SlotRepository()
        self.booking_repo = BookingRepository()

        self.center_service = CenterService(self.center_repo)
        self.workout_admin_service = WorkoutAdminService(self.center_repo, self.slot_repo)
        self.user_service = UserService(self.user_repo)
        self.booking_service = BookingService(
            self.user_repo,
            self.slot_repo,
            self.booking_repo,
        )
        self.availability_service = AvailabilityService(self.slot_repo)


def seed_data(app: ClearFitApp) -> None:
    centers = app.center_service
    admin = app.workout_admin_service

    centers.add_centre("Koramangala")
    centers.add_centre_timings("Koramangala", [(6, 9), (18, 21)])
    centers.add_centre_activities(
        "Koramangala",
        ["Weights", "Cardio", "Yoga", "Swimming"],
    )

    centers.add_centre("Bellandur")
    centers.add_centre_timings("Bellandur", [(7, 10), (19, 22)])
    centers.add_centre_activities("Bellandur", ["Weights", "Cardio", "Yoga"])

    admin.add_workout(AddWorkoutRequest("Koramangala", "Weights", 6, 7, 100))
    admin.add_workout(AddWorkoutRequest("Koramangala", "Cardio", 7, 8, 150))
    admin.add_workout(AddWorkoutRequest("Koramangala", "Yoga", 8, 9, 200))

    admin.add_workout(AddWorkoutRequest("Bellandur", "Cardio", 19, 20, 20))
    admin.add_workout(AddWorkoutRequest("Bellandur", "Weights", 20, 21, 100))
    admin.add_workout(AddWorkoutRequest("Bellandur", "Weights", 21, 22, 100))


def print_availability(title: str, slots: List[SlotView]) -> None:
    print(title)
    for slot in slots:
        print(str(slot))


def main() -> None:
    app = ClearFitApp()
    seed_data(app)

    app.user_service.register("Vaibhav")

    print_availability(
        "Weights availability:",
        app.availability_service.view_workout_availability("Weights"),
    )

    booking = app.booking_service.book_session(
        SessionRequest("Vaibhav", "Koramangala", "Weights", 6, 7)
    )
    print("Booked:", booking.booking_id)

    print_availability(
        "Weights availability after booking:",
        app.availability_service.view_workout_availability("Weights"),
    )

    app.booking_service.cancel_session(
        SessionRequest("Vaibhav", "Koramangala", "Weights", 6, 7)
    )

    print_availability(
        "Koramangala Weights after cancellation:",
        app.availability_service.view_workout_availability("Weights", "Koramangala"),
    )


if __name__ == "__main__":
    main()
