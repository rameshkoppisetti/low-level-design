import uuid
from enum import Enum
from threading import Lock, Thread
from datetime import datetime


# =========================================================
# ENUMS
# =========================================================

class RoomType(Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class BookingStatus(Enum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# =========================================================
# DOMAIN
# =========================================================

class User:

    def __init__(self, name):

        self.id = str(uuid.uuid4())

        self.name = name


class MeetingRoom:

    def __init__(
        self,
        room_number,
        room_type,
        capacity
    ):

        self.id = str(uuid.uuid4())

        self.room_number = room_number

        self.room_type = room_type

        self.capacity = capacity

        self.lock = Lock()

    def __repr__(self):

        return (
            f"MeetingRoom("
            f"room={self.room_number}, "
            f"type={self.room_type.value}, "
            f"capacity={self.capacity})"
        )


class Reservation:

    def __init__(
        self,
        room_id,
        user_id,
        start_time,
        end_time
    ):

        self.id = str(uuid.uuid4())

        self.room_id = room_id

        self.user_id = user_id

        self.start_time = start_time

        self.end_time = end_time


class Booking:

    def __init__(
        self,
        user,
        reservation
    ):

        self.id = str(uuid.uuid4())

        self.user = user

        self.reservation = reservation

        self.status = BookingStatus.RESERVED

    def update_status(self, status):
        self.status = status


# =========================================================
# AVAILABILITY SERVICE
# =========================================================

class AvailabilityService:

    @staticmethod
    def overlaps(
        existing_start,
        existing_end,
        requested_start,
        requested_end
    ):

        return not (
            requested_end <= existing_start
            or
            requested_start >= existing_end
        )

    def is_available(
        self,
        reservations,
        room_id,
        start_time,
        end_time
    ):

        for reservation in reservations:

            if reservation.room_id != room_id:
                continue

            if self.overlaps(
                reservation.start_time,
                reservation.end_time,
                start_time,
                end_time
            ):

                return False

        return True


# =========================================================
# SEARCH SERVICE
# =========================================================

class SearchService:

    def __init__(
        self,
        rooms,
        reservations,
        availability_service
    ):

        self.rooms = rooms

        self.reservations = reservations

        self.availability_service = (
            availability_service
        )

    def search_rooms(
        self,
        start_time,
        end_time,
        min_capacity
    ):

        available_rooms = []

        for room in self.rooms.values():

            if room.capacity < min_capacity:
                continue

            if self.availability_service.is_available(
                self.reservations.values(),
                room.id,
                start_time,
                end_time
            ):

                available_rooms.append(room)

        return available_rooms


# =========================================================
# BOOKING SERVICE
# =========================================================

class BookingService:

    def __init__(self, rooms):

        self.rooms = rooms

        self.reservations = {}

        self.bookings = {}

        self.availability_service = (
            AvailabilityService()
        )

    def book_room(
        self,
        user,
        room_id,
        start_time,
        end_time
    ):

        room = self.rooms.get(room_id)

        if not room:
            raise ValueError(
                "Room not found"
            )

        if start_time >= end_time:
            raise ValueError(
                "Invalid time interval"
            )

        with room.lock:

            # recheck inside lock
            if not self.availability_service.is_available(
                self.reservations.values(),
                room.id,
                start_time,
                end_time
            ):

                raise ValueError(
                    "Room unavailable"
                )

            reservation = Reservation(
                room.id,
                user.id,
                start_time,
                end_time
            )

            self.reservations[
                reservation.id
            ] = reservation

            booking = Booking(
                user,
                reservation
            )

            self.bookings[
                booking.id
            ] = booking

            print(
                f"Room booked -> "
                f"{room.room_number}"
            )

            return booking

    def confirm_booking(
        self,
        booking_id
    ):

        booking = self.bookings.get(
            booking_id
        )

        if not booking:
            raise ValueError(
                "Booking not found"
            )

        if booking.status != BookingStatus.RESERVED:
            return booking

        booking.update_status(
            BookingStatus.CONFIRMED
        )

        return booking

    def cancel_booking(
        self,
        booking_id
    ):

        booking = self.bookings.get(
            booking_id
        )

        if not booking:
            raise ValueError(
                "Booking not found"
            )

        if booking.status == BookingStatus.CANCELLED:
            return booking

        booking.update_status(
            BookingStatus.CANCELLED
        )

        del self.reservations[
            booking.reservation.id
        ]

        return booking


# =========================================================
# DEMO
# =========================================================

def main():

    rooms = {}

    room1 = MeetingRoom(
        "A101",
        RoomType.SMALL,
        4
    )

    room2 = MeetingRoom(
        "B201",
        RoomType.LARGE,
        10
    )

    rooms[room1.id] = room1
    rooms[room2.id] = room2

    user = User("satya")

    booking_service = BookingService(
        rooms
    )

    search_service = SearchService(
        rooms,
        booking_service.reservations,
        booking_service.availability_service
    )

    start_time = datetime(
        2026, 5, 20, 10, 0
    )

    end_time = datetime(
        2026, 5, 20, 12, 0
    )

    available_rooms = (
        search_service.search_rooms(
            start_time,
            end_time,
            3
        )
    )

    print(
        "Available Rooms:",
        available_rooms
    )

    # =====================================================
    # CONCURRENT BOOKING TEST
    # =====================================================

    def book():

        try:

            booking = (
                booking_service.book_room(
                    user,
                    room1.id,
                    start_time,
                    end_time
                )
            )

            print(
                f"Success -> "
                f"{booking.id}"
            )

        except Exception as e:

            print(
                f"Booking failed -> {e}"
            )

    t1 = Thread(target=book)
    t2 = Thread(target=book)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # =====================================================
    # CONFIRM BOOKING
    # =====================================================

    booking = list(
        booking_service.bookings.values()
    )[0]

    booking = (
        booking_service.confirm_booking(
            booking.id
        )
    )

    print(
        f"Booking Status -> "
        f"{booking.status.value}"
    )

    # =====================================================
    # CANCEL BOOKING
    # =====================================================

    booking = (
        booking_service.cancel_booking(
            booking.id
        )
    )

    print(
        f"Booking Status -> "
        f"{booking.status.value}"
    )


if __name__ == "__main__":
    main()