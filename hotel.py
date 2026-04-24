import uuid
import threading
from datetime import date
from enum import Enum
from typing import List, Dict


# =========================
# ENUMS
# =========================

class BookingStatus(Enum):
    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"


# =========================
# DOMAIN
# =========================

class Guest:
    def __init__(self, guest_id: str, name: str):
        self.id = guest_id
        self.name = name


class Room:
    def __init__(self, room_id: str, room_type: str, base_price: float):
        self.id = room_id
        self.type = room_type
        self.base_price = base_price


class Booking:
    def __init__(self, guest: Guest, room: Room, start: date, end: date):
        self.id = str(uuid.uuid4())
        self.guest = guest
        self.room = room
        self.start = start
        self.end = end
        self.status = BookingStatus.CREATED
        self.amount = 0.0

    def confirm(self):
        self.status = BookingStatus.CONFIRMED

    def check_in(self):
        self.status = BookingStatus.CHECKED_IN

    def check_out(self):
        self.status = BookingStatus.CHECKED_OUT

    def cancel(self):
        self.status = BookingStatus.CANCELLED


# =========================
# STRATEGIES
# =========================

class PricingStrategy:
    def calculate(self, room: Room, start: date, end: date) -> float:
        days = (end - start).days
        return room.base_price * days


class SeasonalPricing(PricingStrategy):
    def calculate(self, room: Room, start: date, end: date) -> float:
        base = super().calculate(room, start, end)
        return base * 1.2  # surge pricing


class CancellationPolicy:
    def can_cancel(self, booking: Booking) -> bool:
        return booking.status in [BookingStatus.CREATED, BookingStatus.CONFIRMED]


# =========================
# THREAD-SAFE AVAILABILITY
# =========================

class RoomAvailabilityService:
    def __init__(self):
        self.room_bookings: Dict[str, List] = {}  # room_id -> [(start, end)]
        self.locks: Dict[str, threading.Lock] = {}  # room_id -> lock

    def _get_lock(self, room_id):
        if room_id not in self.locks:
            self.locks[room_id] = threading.Lock()
        return self.locks[room_id]

    def is_available(self, room_id, start, end):
        bookings = self.room_bookings.get(room_id, [])
        for s, e in bookings:
            if not (end <= s or start >= e):
                return False
        return True

    def reserve(self, room_id, start, end) -> bool:
        lock = self._get_lock(room_id)

        with lock:  # 🔥 CRITICAL
            if not self.is_available(room_id, start, end):
                return False

            if room_id not in self.room_bookings:
                self.room_bookings[room_id] = []

            self.room_bookings[room_id].append((start, end))
            return True

    def release(self, room_id, start, end):
        lock = self._get_lock(room_id)

        with lock:
            if room_id in self.room_bookings:
                self.room_bookings[room_id].remove((start, end))


# =========================
# SERVICES
# =========================


class SearchService:
    def __init__(self, availability_service: RoomAvailabilityService):
        self.availability = availability_service

    def search(self, rooms: List[Room], room_type: str, start, end):
        result = []

        for room in rooms:
            if room.type != room_type:
                continue

            if self.availability.is_available(room.id, start, end):
                result.append(room)

        return result

class BookingService:
    def __init__(self, availability_service: RoomAvailabilityService,
                 pricing: PricingStrategy,
                 cancellation_policy: CancellationPolicy):
        self.availability = availability_service
        self.pricing = pricing
        self.cancellation_policy = cancellation_policy
        self.bookings = {}

    def create_booking(self, guest: Guest, room: Room, start: date, end: date):
        if not self.availability.reserve(room.id, start, end):
            print("❌ Room not available")
            return None

        booking = Booking(guest, room, start, end)
        booking.amount = self.pricing.calculate(room, start, end)
        booking.confirm()

        self.bookings[booking.id] = booking

        print(f"✅ Booking confirmed: {booking.id}")
        return booking

    def cancel_booking(self, booking_id):
        booking = self.bookings.get(booking_id)

        if not booking:
            return

        if not self.cancellation_policy.can_cancel(booking):
            print("❌ Cannot cancel")
            return

        booking.cancel()
        self.availability.release(booking.room.id, booking.start, booking.end)

        print("❌ Booking cancelled")

    def check_in(self, booking_id):
        booking = self.bookings.get(booking_id)
        booking.check_in()
        print("🏨 Checked in")

    def check_out(self, booking_id):
        booking = self.bookings.get(booking_id)
        booking.check_out()
        print("🏁 Checked out")


# =========================
# DEMO
# =========================

def main():
    availability = RoomAvailabilityService()
    pricing = SeasonalPricing()
    cancellation = CancellationPolicy()

    booking_service = BookingService(availability, pricing, cancellation)
    search_service = SearchService(availability)

    # rooms
    rooms = [
        Room("101", "DELUXE", 2000),
        Room("102", "DELUXE", 2200),
        Room("201", "STANDARD", 1500),
    ]

    guest = Guest("g1", "Satya")

    start = date(2026, 4, 20)
    end = date(2026, 4, 22)

    # 🔍 SEARCH BEFORE BOOKING
    print("\n🔍 Available rooms before booking:")
    available = search_service.search(rooms, "DELUXE", start, end)
    print([r.id for r in available])

    # booking
    booking = booking_service.create_booking(guest, rooms[0], start, end)

    # 🔍 SEARCH AFTER BOOKING
    print("\n🔍 Available rooms after booking:")
    available = search_service.search(rooms, "DELUXE", start, end)
    print([r.id for r in available])

    if booking:
        booking_service.check_in(booking.id)
        booking_service.check_out(booking.id)

    # overlapping booking attempt
    print("\n⚠️ Trying overlapping booking:")
    booking2 = booking_service.create_booking(guest, rooms[0], start, end)


if __name__ == "__main__":
    main()