import uuid
from enum import Enum
from threading import Lock, Thread
from datetime import datetime
from abc import ABC, abstractmethod


# =========================================================
# DOMAIN
# =========================================================

class VehicleType(Enum):
    SEDAN = "SEDAN"
    SUV = "SUV"
    HATCHBACK = "HATCHBACK"


class BookingStatus(Enum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class User:

    def __init__(self, name):

        self.id = str(uuid.uuid4())

        self.name = name


class Vehicle:

    def __init__(
        self,
        number,
        vehicle_type,
        price_per_hour
    ):

        self.id = str(uuid.uuid4())

        self.number = number

        self.vehicle_type = vehicle_type

        self.price_per_hour = price_per_hour

        self.lock = Lock()

    def __repr__(self):

        return (
            f"Vehicle("
            f"number={self.number}, "
            f"type={self.vehicle_type.value})"
        )


class Reservation:

    def __init__(
        self,
        vehicle_id,
        user_id,
        start_time,
        end_time
    ):

        self.id = str(uuid.uuid4())

        self.vehicle_id = vehicle_id

        self.user_id = user_id

        self.start_time = start_time

        self.end_time = end_time


class Booking:

    def __init__(
        self,
        user,
        reservation,
        total_price
    ):

        self.id = str(uuid.uuid4())

        self.user = user

        self.reservation = reservation

        self.total_price = total_price

        self.status = BookingStatus.RESERVED

    def update_status(self, status):
        self.status = status


# =========================================================
# PAYMENT STRATEGY
# =========================================================

class PaymentStrategy(ABC):

    @abstractmethod
    def pay(self, booking, amount):
        pass

    @abstractmethod
    def refund(self, booking, amount):
        pass


class UpiPayment(PaymentStrategy):

    def pay(self, booking, amount):

        print(
            f"Payment success "
            f"booking={booking.id} "
            f"amount={amount}"
        )

        return True

    def refund(self, booking, amount):

        print(
            f"Refund success "
            f"booking={booking.id} "
            f"amount={amount}"
        )

        return True


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
        vehicle_id,
        start_time,
        end_time
    ):

        for reservation in reservations:

            if reservation.vehicle_id != vehicle_id:
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
        vehicles,
        availability_service,
        reservations
    ):

        self.vehicles = vehicles

        self.availability_service = (
            availability_service
        )

        self.reservations = reservations

    def search(
        self,
        vehicle_type,
        start_time,
        end_time
    ):

        available_vehicles = []

        for vehicle in self.vehicles.values():

            if vehicle.vehicle_type != vehicle_type:
                continue

            if self.availability_service.is_available(
                self.reservations.values(),
                vehicle.id,
                start_time,
                end_time
            ):

                available_vehicles.append(vehicle)

        return available_vehicles


# =========================================================
# RENTAL SERVICE
# =========================================================

class RentalService:

    def __init__(
        self,
        vehicles,
        payment_strategy
    ):

        self.vehicles = vehicles

        self.payment_strategy = payment_strategy

        self.availability_service = (
            AvailabilityService()
        )

        self.reservations = {}

        self.bookings = {}

    def calculate_price(
        self,
        vehicle,
        start_time,
        end_time
    ):

        duration_hours = (
            end_time - start_time
        ).seconds / 3600

        return (
            duration_hours *
            vehicle.price_per_hour
        )

    def reserve_vehicle(
        self,
        user,
        vehicle_id,
        start_time,
        end_time
    ):

        vehicle = self.vehicles.get(vehicle_id)

        if not vehicle:
            raise ValueError(
                "Vehicle not found"
            )

        with vehicle.lock:

            # --------------------------------------------
            # RECHECK INSIDE LOCK
            # prevents double booking
            # --------------------------------------------
            if not self.availability_service.is_available(
                self.reservations.values(),
                vehicle.id,
                start_time,
                end_time
            ):

                raise ValueError(
                    "Vehicle unavailable"
                )

            reservation = Reservation(
                vehicle.id,
                user.id,
                start_time,
                end_time
            )

            self.reservations[
                reservation.id
            ] = reservation

            total_price = self.calculate_price(
                vehicle,
                start_time,
                end_time
            )

            booking = Booking(
                user,
                reservation,
                total_price
            )

            self.bookings[booking.id] = booking

            print(
                f"Vehicle reserved "
                f"booking={booking.id}"
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

        payment_success = (
            self.payment_strategy.pay(
                booking,
                booking.total_price
            )
        )

        if not payment_success:

            booking.update_status(
                BookingStatus.CANCELLED
            )

            del self.reservations[
                booking.reservation.id
            ]

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

        if booking.status == BookingStatus.CONFIRMED:

            self.payment_strategy.refund(
                booking,
                booking.total_price
            )

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

    vehicles = {}

    car1 = Vehicle(
        "KA01AB1234",
        VehicleType.SEDAN,
        100
    )

    car2 = Vehicle(
        "KA02CD5678",
        VehicleType.SUV,
        200
    )

    vehicles[car1.id] = car1
    vehicles[car2.id] = car2

    user = User("satya")

    rental_service = RentalService(
        vehicles,
        UpiPayment()
    )

    search_service = SearchService(
        vehicles,
        rental_service.availability_service,
        rental_service.reservations
    )

    start_time = datetime(
        2026, 5, 20, 10, 0
    )

    end_time = datetime(
        2026, 5, 20, 15, 0
    )

    available = search_service.search(
        VehicleType.SEDAN,
        start_time,
        end_time
    )

    print("Available:", available)

    # =====================================================
    # CONCURRENT BOOKING TEST
    # =====================================================

    def book_vehicle():

        try:

            booking = (
                rental_service.reserve_vehicle(
                    user,
                    car1.id,
                    start_time,
                    end_time
                )
            )

            print(
                f"Reserved -> {booking.id}"
            )

        except Exception as e:

            print(
                f"Booking failed -> {e}"
            )

    t1 = Thread(target=book_vehicle)
    t2 = Thread(target=book_vehicle)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # =====================================================
    # CONFIRM BOOKING
    # =====================================================

    booking = list(
        rental_service.bookings.values()
    )[0]

    booking = rental_service.confirm_booking(
        booking.id
    )

    print(
        f"Booking Status -> "
        f"{booking.status.value}"
    )

    # =====================================================
    # CANCEL BOOKING
    # =====================================================

    booking = rental_service.cancel_booking(
        booking.id
    )

    print(
        f"Booking Status -> "
        f"{booking.status.value}"
    )


if __name__ == "__main__":
    main()