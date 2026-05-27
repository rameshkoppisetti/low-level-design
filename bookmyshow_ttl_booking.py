import threading
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional


class SeatCategory(Enum):
    SILVER = 1
    GOLD = 2
    VIP = 3


class SeatStatus(Enum):
    AVAILABLE = 1
    RESERVED = 2
    BOOKED = 3


class BookingState(Enum):
    PENDING = 1
    CONFIRMED = 2
    CANCELLED = 3
    EXPIRED = 4


class PricingStrategy:
    def calculate_price(self, category: SeatCategory, is_weekend: bool) -> float:
        raise NotImplementedError


class DynamicPricingStrategy(PricingStrategy):
    def calculate_price(self, category: SeatCategory, is_weekend: bool) -> float:
        if category == SeatCategory.SILVER:
            base = 100.0
        elif category == SeatCategory.GOLD:
            base = 150.0
        else:
            base = 250.0

        return base * 1.25 if is_weekend else base


class Seat:
    def __init__(self, seat_id: str, category: SeatCategory):
        self.id = seat_id
        self.category = category
        self.status = SeatStatus.AVAILABLE
        self.reservation_time = 0.0
        self.lock = threading.RLock()

    def get_status(self, ttl_ms: float) -> SeatStatus:
        if self._is_expired(ttl_ms):
            self.status = SeatStatus.AVAILABLE
            self.reservation_time = 0.0
        return self.status

    def reserve(self, ttl_ms: float) -> bool:
        if self.get_status(ttl_ms) != SeatStatus.AVAILABLE:
            return False

        self.status = SeatStatus.RESERVED
        self.reservation_time = self._now_ms()
        return True

    def book(self) -> bool:
        if self.status != SeatStatus.RESERVED:
            return False

        self.status = SeatStatus.BOOKED
        self.reservation_time = 0.0
        return True

    def release(self) -> None:
        if self.status == SeatStatus.RESERVED:
            self.status = SeatStatus.AVAILABLE
            self.reservation_time = 0.0

    def _is_expired(self, ttl_ms: float) -> bool:
        return (
            self.status == SeatStatus.RESERVED
            and self._now_ms() - self.reservation_time > ttl_ms
        )

    def _now_ms(self) -> float:
        return time.time() * 1000


class Show:
    def __init__(
        self,
        show_id: str,
        movie: str,
        is_weekend: bool,
        silver_count: int,
        gold_count: int,
        vip_count: int,
    ):
        self.id = show_id
        self.movie = movie
        self.is_weekend = is_weekend
        self.seats: Dict[str, Seat] = {}
        self._create_seats(silver_count, gold_count, vip_count)

    def _create_seats(
        self,
        silver_count: int,
        gold_count: int,
        vip_count: int,
    ) -> None:
        idx = 1

        for _ in range(silver_count):
            seat_id = f"S{idx}"
            self.seats[seat_id] = Seat(seat_id, SeatCategory.SILVER)
            idx += 1

        for _ in range(gold_count):
            seat_id = f"S{idx}"
            self.seats[seat_id] = Seat(seat_id, SeatCategory.GOLD)
            idx += 1

        for _ in range(vip_count):
            seat_id = f"S{idx}"
            self.seats[seat_id] = Seat(seat_id, SeatCategory.VIP)
            idx += 1


class Booking:
    def __init__(
        self,
        booking_id: str,
        show: Show,
        seats: List[Seat],
        amount: float,
    ):
        self.id = booking_id
        self.show = show
        self.seats = seats
        self.amount = amount
        self.state = BookingState.PENDING
        self.created_at = time.time() * 1000
        self.lock = threading.RLock()


class BookingService:
    def __init__(
        self,
        ttl_ms: float,
        pricing_strategy: Optional[PricingStrategy] = None,
    ):
        self.ttl_ms = ttl_ms
        self.bookings: Dict[str, Booking] = {}
        self.pricing_strategy = pricing_strategy or DynamicPricingStrategy()
        self.booking_lock = threading.RLock()

    def create_booking(self, show: Show, seat_ids: List[str]) -> Optional[Booking]:
        target_seats = self._get_sorted_seats(show, seat_ids)
        if not target_seats:
            return None

        acquired = []

        for seat in target_seats:
            seat.lock.acquire()
            acquired.append(seat)

        try:
            reserved = []

            for seat in target_seats:
                if not seat.reserve(self.ttl_ms):
                    for reserved_seat in reserved:
                        reserved_seat.release()
                    return None
                reserved.append(seat)

            total_amount = sum(
                self.pricing_strategy.calculate_price(
                    seat.category,
                    show.is_weekend,
                )
                for seat in target_seats
            )

            booking_id = f"BKG-{uuid.uuid4().hex[:8].upper()}"
            booking = Booking(booking_id, show, target_seats, total_amount)

            with self.booking_lock:
                self.bookings[booking_id] = booking

            return booking
        finally:
            for seat in reversed(acquired):
                seat.lock.release()

    def confirm_booking(self, booking_id: str) -> bool:
        booking = self.bookings.get(booking_id)
        if not booking:
            return False

        with booking.lock:
            if booking.state != BookingState.PENDING:
                return False

            if self._booking_expired(booking):
                self._expire_booking(booking)
                return False

            self._lock_seats(booking.seats)
            try:
                for seat in booking.seats:
                    if seat.status != SeatStatus.RESERVED:
                        self._expire_booking(booking)
                        return False

                for seat in booking.seats:
                    seat.book()

                booking.state = BookingState.CONFIRMED
                return True
            finally:
                self._unlock_seats(booking.seats)

    def cancel_booking(self, booking_id: str) -> bool:
        booking = self.bookings.get(booking_id)
        if not booking:
            return False

        with booking.lock:
            if booking.state != BookingState.PENDING:
                return False

            self._release_booking(booking, BookingState.CANCELLED)
            return True

    def cleanup_expired_bookings(self) -> None:
        for booking in list(self.bookings.values()):
            with booking.lock:
                if (
                    booking.state == BookingState.PENDING
                    and self._booking_expired(booking)
                ):
                    self._expire_booking(booking)

    def _get_sorted_seats(self, show: Show, seat_ids: List[str]) -> Optional[List[Seat]]:
        if len(set(seat_ids)) != len(seat_ids):
            return None

        seats = []

        for seat_id in seat_ids:
            seat = show.seats.get(seat_id)
            if not seat:
                return None
            seats.append(seat)

        return sorted(seats, key=lambda seat: seat.id)

    def _booking_expired(self, booking: Booking) -> bool:
        return time.time() * 1000 - booking.created_at > self.ttl_ms

    def _expire_booking(self, booking: Booking) -> None:
        self._release_booking(booking, BookingState.EXPIRED)

    def _release_booking(self, booking: Booking, state: BookingState) -> None:
        self._lock_seats(booking.seats)
        try:
            for seat in booking.seats:
                seat.release()
            booking.state = state
        finally:
            self._unlock_seats(booking.seats)

    def _lock_seats(self, seats: List[Seat]) -> None:
        for seat in sorted(seats, key=lambda seat: seat.id):
            seat.lock.acquire()

    def _unlock_seats(self, seats: List[Seat]) -> None:
        for seat in sorted(seats, key=lambda seat: seat.id, reverse=True):
            seat.lock.release()


if __name__ == "__main__":
    print("=== RUNNING BMS PYTHON DRIVER ===")
    service = BookingService(1500)
    show = Show("SHOW-99", "Gladiator II", True, 4, 2, 1)

    booking_a = service.create_booking(show, ["S1", "S2"])
    print(f"User A holds S1, S2 -> Booking ID: {booking_a.id}, Total: ${booking_a.amount}")

    booking_b = service.create_booking(show, ["S2", "S3"])
    print(
        "User B holds S2, S3 -> Result: "
        f"{'SUCCESS' if booking_b else 'FAILED (Conflict Rollback verified)'}"
    )

    result = service.confirm_booking(booking_a.id)
    print(f"User A checkout -> {'SUCCESS' if result else 'FAILED'}")

    booking_c = service.create_booking(show, ["S3", "S4"])
    print(f"User C holds S3, S4 -> Booking ID: {booking_c.id}. Waiting to expire...")

    time.sleep(2.0)
    service.cleanup_expired_bookings()
    print(f"User C booking state after timeout -> {booking_c.state.name}")

    booking_d = service.create_booking(show, ["S3", "S4"])
    print(f"User D holds S3, S4 -> Result: {'SUCCESS' if booking_d else 'FAILED'}")
