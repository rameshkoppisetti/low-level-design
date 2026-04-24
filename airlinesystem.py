import uuid
from threading import Lock
from enum import Enum


# =========================
# ENUMS
# =========================

class SeatStatus(Enum):
    AVAILABLE = 1
    LOCKED = 2
    BOOKED = 3


class BookingStatus(Enum):
    PENDING = 1
    CONFIRMED = 2
    CANCELLED = 3


class TicketStatus(Enum):
    PENDING = 1
    CONFIRMED = 2
    CANCELLED = 3


# =========================
# DOMAIN
# =========================

class Seat:
    def __init__(self, seat_number):
        self.seat_number = seat_number
        self.status = SeatStatus.AVAILABLE
        self.lock = Lock()


class Flight:
    def __init__(self, id, seats):
        self.id = id
        self.seats = {s.seat_number: s for s in seats}

    def get_seat(self, seat_number):
        return self.seats.get(seat_number)


class Passenger:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Ticket:
    def __init__(self, passenger_id, seat_number):
        self.id = uuid.uuid4()
        self.passenger_id = passenger_id
        self.seat_number = seat_number
        self.status = TicketStatus.PENDING


class Booking:
    def __init__(self, flight_id, tickets):
        self.id = uuid.uuid4()
        self.flight_id = flight_id
        self.tickets = tickets
        self.status = BookingStatus.PENDING


# =========================
# SEAT SERVICE (CONCURRENCY)
# =========================

class SeatService:
    def __init__(self, flight: Flight):
        self.flight = flight

    def lock_seats(self, seat_numbers):
        locked_seats = []

        for sn in sorted(seat_numbers):
            seat = self.flight.get_seat(sn)
            seat.lock.acquire()
            locked_seats.append(seat)

        try:
            for seat in locked_seats:
                if seat.status != SeatStatus.AVAILABLE:
                    raise ValueError(f"Seat {seat.seat_number} not available")

            for seat in locked_seats:
                seat.status = SeatStatus.LOCKED

            return locked_seats

        except:
            for seat in locked_seats:
                seat.lock.release()
            raise

    def confirm_seats(self, seats):
        for seat in seats:
            seat.status = SeatStatus.BOOKED

    def release_seats(self, seats):
        for seat in seats:
            seat.status = SeatStatus.AVAILABLE


# =========================
# PAYMENT STRATEGY
# =========================

class PaymentStrategy:
    def pay(self, amount):
        raise NotImplementedError


class DummyPayment(PaymentStrategy):
    def pay(self, amount):
        print(f"Payment of ₹{amount} successful")
        return True


# =========================
# BOOKING SERVICE
# =========================

class BookingService:
    def __init__(self, flight: Flight, payment_strategy):
        self.flight = flight
        self.seat_service = SeatService(flight)
        self.payment = payment_strategy
        self.bookings = {}

    def create_booking(self, passengers, seat_numbers):
        # 1. lock seats
        locked_seats = self.seat_service.lock_seats(seat_numbers)

        try:
            # 2. create tickets
            tickets = []
            for p, sn in zip(passengers, seat_numbers):
                tickets.append(Ticket(p.id, sn))

            # 3. create booking
            booking = Booking(self.flight.id, tickets)
            self.bookings[booking.id] = booking

            return booking, locked_seats

        finally:
            for seat in locked_seats:
                seat.lock.release()

    def confirm_booking(self, booking_id, locked_seats):
        booking = self.bookings.get(booking_id)

        if not booking:
            raise ValueError("Booking not found")

        # 4. payment
        if not self.payment.pay(len(booking.tickets) * 1000):
            booking.status = BookingStatus.CANCELLED
            for t in booking.tickets:
                t.status = TicketStatus.CANCELLED

            self.seat_service.release_seats(locked_seats)
            return booking

        # 5. confirm
        booking.status = BookingStatus.CONFIRMED
        for t in booking.tickets:
            t.status = TicketStatus.CONFIRMED

        self.seat_service.confirm_seats(locked_seats)

        return booking


# =========================
# DEMO
# =========================

def main():
    seats = [Seat("1A"), Seat("1B"), Seat("1C")]
    flight = Flight("F1", seats)

    passengers = [
        Passenger("p1", "Satya"),
        Passenger("p2", "Rahul"),
    ]

    service = BookingService(flight, DummyPayment())

    # Step 1: create booking (locks seats)
    booking, locked_seats = service.create_booking(
        passengers, ["1A", "1B"]
    )

    print("Booking Created:", booking.status)

    # Step 2: confirm booking (payment + final)
    booking = service.confirm_booking(booking.id, locked_seats)

    print("Final Status:", booking.status)

    for seat in flight.seats.values():
        print(seat.seat_number, seat.status)


if __name__ == "__main__":
    main()