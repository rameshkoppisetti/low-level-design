import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock, Thread
from typing import Dict, List, Optional


# =========================================================
# DOMAIN
# =========================================================

class VehicleType(Enum):
    SEDAN = "SEDAN"
    SUV = "SUV"
    HATCHBACK = "HATCHBACK"


class VehicleStatus(Enum):
    AVAILABLE = "AVAILABLE"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"


class BookingStatus(Enum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentMode(Enum):
    UPI = "UPI"
    CASH = "CASH"
    CARD = "CARD"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class BookingRejectedError(Exception):
    pass


@dataclass(frozen=True)
class User:
    user_id: str
    name: str
    email: str


@dataclass
class Vehicle:
    vehicle_id: str
    number: str
    name: str
    vehicle_type: VehicleType
    price_per_hour: int
    status: VehicleStatus = VehicleStatus.AVAILABLE
    lock: RLock = RLock()


@dataclass
class Booking:
    booking_id: str
    user: User
    vehicle: Vehicle
    start_time: datetime
    end_time: datetime
    amount: int
    payment_mode: PaymentMode
    status: BookingStatus = BookingStatus.RESERVED
    fine: int = 0


# =========================================================
# STRATEGIES / PAYMENT MODULE
# =========================================================

class PricingStrategy(ABC):
    @abstractmethod
    def calculate_price(
        self,
        vehicle: Vehicle,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        pass


class HourlyPricingStrategy(PricingStrategy):
    def calculate_price(
        self,
        vehicle: Vehicle,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        hours = _duration_hours_rounded_up(start_time, end_time)
        return hours * vehicle.price_per_hour


class FineStrategy(ABC):
    @abstractmethod
    def calculate_fine(self, expected_return: datetime, actual_return: datetime) -> int:
        pass


class FlatFineStrategy(FineStrategy):
    def __init__(self, fine_per_hour: int = 50):
        self.fine_per_hour = fine_per_hour

    def calculate_fine(self, expected_return: datetime, actual_return: datetime) -> int:
        if actual_return <= expected_return:
            return 0
        return _duration_hours_rounded_up(expected_return, actual_return) * self.fine_per_hour


class PaymentModule(ABC):
    @abstractmethod
    def pay(self, booking: Booking, amount: int) -> bool:
        pass

    @abstractmethod
    def refund(self, booking: Booking, amount: int) -> bool:
        pass


class UpiPayment(PaymentModule):
    def pay(self, booking: Booking, amount: int) -> bool:
        print(f"Payment success booking={booking.booking_id} amount={amount}")
        return True

    def refund(self, booking: Booking, amount: int) -> bool:
        print(f"Refund success booking={booking.booking_id} amount={amount}")
        return True


# =========================================================
# REPOSITORY
# =========================================================

class VehicleRepository:
    def __init__(self):
        self.vehicles: Dict[str, Vehicle] = {}
        self._lock = RLock()

    def add(self, vehicle: Vehicle) -> None:
        with self._lock:
            if vehicle.vehicle_id in self.vehicles:
                raise ValidationError(f"Vehicle already exists: {vehicle.vehicle_id}")
            self.vehicles[vehicle.vehicle_id] = vehicle

    def get(self, vehicle_id: str) -> Vehicle:
        with self._lock:
            vehicle = self.vehicles.get(vehicle_id)
            if not vehicle:
                raise NotFoundError(f"Vehicle not found: {vehicle_id}")
            return vehicle

    def list_all(self) -> List[Vehicle]:
        with self._lock:
            return list(self.vehicles.values())


class BookingRepository:
    def __init__(self):
        self.bookings: Dict[str, Booking] = {}
        self.bookings_by_vehicle: Dict[str, set[str]] = {}
        self._lock = RLock()

    def add(self, booking: Booking) -> None:
        with self._lock:
            self.bookings[booking.booking_id] = booking
            self.bookings_by_vehicle.setdefault(booking.vehicle.vehicle_id, set()).add(
                booking.booking_id
            )

    def get(self, booking_id: str) -> Booking:
        with self._lock:
            booking = self.bookings.get(booking_id)
            if not booking:
                raise NotFoundError(f"Booking not found: {booking_id}")
            return booking

    def list_by_vehicle(self, vehicle_id: str) -> List[Booking]:
        with self._lock:
            return [
                self.bookings[booking_id]
                for booking_id in self.bookings_by_vehicle.get(vehicle_id, set())
            ]


# =========================================================
# SERVICE
# =========================================================

class SearchService:
    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        booking_repo: BookingRepository,
    ):
        self.vehicle_repo = vehicle_repo
        self.booking_repo = booking_repo

    def search_by_type(
        self,
        vehicle_type: VehicleType,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Vehicle]:
        _validate_time_range(start_time, end_time)
        result = []

        for vehicle in self.vehicle_repo.list_all():
            if vehicle.vehicle_type != vehicle_type:
                continue
            if vehicle.status != VehicleStatus.AVAILABLE:
                continue
            if self.is_available(vehicle.vehicle_id, start_time, end_time):
                result.append(vehicle)

        return sorted(result, key=lambda item: (item.price_per_hour, item.number))

    def is_available(
        self,
        vehicle_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        for booking in self.booking_repo.list_by_vehicle(vehicle_id):
            if booking.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
                continue
            if _overlaps(start_time, end_time, booking.start_time, booking.end_time):
                return False
        return True


class CarRentalService:
    def __init__(
        self,
        vehicle_repo: VehicleRepository,
        booking_repo: BookingRepository,
        search_service: SearchService,
        pricing_strategy: PricingStrategy,
        fine_strategy: FineStrategy,
        payment_module: PaymentModule,
    ):
        self.vehicle_repo = vehicle_repo
        self.booking_repo = booking_repo
        self.search_service = search_service
        self.pricing_strategy = pricing_strategy
        self.fine_strategy = fine_strategy
        self.payment_module = payment_module

    def issue_car(
        self,
        user: User,
        vehicle_id: str,
        start_time: datetime,
        end_time: datetime,
        payment_mode: PaymentMode,
    ) -> Booking:
        _validate_time_range(start_time, end_time)
        vehicle = self.vehicle_repo.get(vehicle_id)

        with vehicle.lock:
            if vehicle.status != VehicleStatus.AVAILABLE:
                raise BookingRejectedError("Vehicle is not available")
            if not self.search_service.is_available(vehicle_id, start_time, end_time):
                raise BookingRejectedError("Vehicle already booked for this time slot")

            amount = self.pricing_strategy.calculate_price(
                vehicle,
                start_time,
                end_time,
            )
            booking = Booking(
                booking_id=f"BKG-{uuid.uuid4().hex[:8].upper()}",
                user=user,
                vehicle=vehicle,
                start_time=start_time,
                end_time=end_time,
                amount=amount,
                payment_mode=payment_mode,
            )
            self.booking_repo.add(booking)

        if self.payment_module.pay(booking, amount):
            booking.status = BookingStatus.CONFIRMED
        else:
            booking.status = BookingStatus.CANCELLED

        return booking

    def cancel_booking(self, booking_id: str) -> Booking:
        booking = self.booking_repo.get(booking_id)

        with booking.vehicle.lock:
            if booking.status == BookingStatus.CANCELLED:
                return booking
            if booking.status == BookingStatus.COMPLETED:
                raise ValidationError("Completed booking cannot be cancelled")
            if booking.status == BookingStatus.CONFIRMED:
                self.payment_module.refund(booking, booking.amount)
            booking.status = BookingStatus.CANCELLED
            return booking

    def return_car(self, booking_id: str, actual_return: datetime) -> Booking:
        booking = self.booking_repo.get(booking_id)

        with booking.vehicle.lock:
            if booking.status != BookingStatus.CONFIRMED:
                raise ValidationError("Only confirmed booking can be returned")
            booking.fine = self.fine_strategy.calculate_fine(
                booking.end_time,
                actual_return,
            )
            booking.status = BookingStatus.COMPLETED
            return booking


# =========================================================
# CONTROLLER
# =========================================================

class CarRentalController:
    def __init__(
        self,
        search_service: SearchService,
        rental_service: CarRentalService,
    ):
        self.search_service = search_service
        self.rental_service = rental_service

    def search_by_car_type(
        self,
        vehicle_type: VehicleType,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Vehicle]:
        return self.search_service.search_by_type(vehicle_type, start_time, end_time)

    def issue_car(
        self,
        user: User,
        vehicle_id: str,
        start_time: datetime,
        end_time: datetime,
        payment_mode: PaymentMode,
    ) -> Booking:
        return self.rental_service.issue_car(
            user,
            vehicle_id,
            start_time,
            end_time,
            payment_mode,
        )

    def cancel_booking(self, booking_id: str) -> Booking:
        return self.rental_service.cancel_booking(booking_id)

    def return_car(self, booking_id: str, actual_return: datetime) -> Booking:
        return self.rental_service.return_car(booking_id, actual_return)


class CarRentalApp:
    def __init__(self):
        self.vehicle_repo = VehicleRepository()
        self.booking_repo = BookingRepository()
        self.search_service = SearchService(self.vehicle_repo, self.booking_repo)
        self.rental_service = CarRentalService(
            self.vehicle_repo,
            self.booking_repo,
            self.search_service,
            HourlyPricingStrategy(),
            FlatFineStrategy(),
            UpiPayment(),
        )
        self.controller = CarRentalController(
            self.search_service,
            self.rental_service,
        )


# =========================================================
# HELPERS / DEMO TESTS
# =========================================================

def _overlaps(start_1: datetime, end_1: datetime, start_2: datetime, end_2: datetime) -> bool:
    return start_1 < end_2 and start_2 < end_1


def _validate_time_range(start_time: datetime, end_time: datetime) -> None:
    if end_time <= start_time:
        raise ValidationError("End time must be after start time")


def _duration_hours_rounded_up(start_time: datetime, end_time: datetime) -> int:
    seconds = (end_time - start_time).total_seconds()
    return int((seconds + 3599) // 3600)


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(app: CarRentalApp) -> None:
    app.vehicle_repo.add(
        Vehicle("v1", "KA01AB1234", "Honda City", VehicleType.SEDAN, 100)
    )
    app.vehicle_repo.add(
        Vehicle("v2", "KA02CD5678", "Innova", VehicleType.SUV, 200)
    )
    app.vehicle_repo.add(
        Vehicle("v3", "KA03EF9999", "Swift", VehicleType.HATCHBACK, 80)
    )


def test_search_and_issue_car() -> None:
    app = CarRentalApp()
    seed_data(app)
    user = User("u1", "Satya", "satya@email.com")
    start = datetime(2026, 5, 20, 10, 0)
    end = datetime(2026, 5, 20, 15, 0)

    available = app.controller.search_by_car_type(VehicleType.SEDAN, start, end)
    assert_equal(["KA01AB1234"], [vehicle.number for vehicle in available], "sedan available")

    booking = app.controller.issue_car(user, "v1", start, end, PaymentMode.UPI)
    assert_equal(BookingStatus.CONFIRMED, booking.status, "booking confirmed")
    assert_equal(500, booking.amount, "hourly price calculated")


def test_overlapping_booking_rejected() -> None:
    app = CarRentalApp()
    seed_data(app)
    user = User("u1", "Satya", "satya@email.com")
    start = datetime(2026, 5, 20, 10, 0)
    end = datetime(2026, 5, 20, 15, 0)

    app.controller.issue_car(user, "v1", start, end, PaymentMode.UPI)

    rejected = False
    try:
        app.controller.issue_car(user, "v1", start, end, PaymentMode.UPI)
    except BookingRejectedError:
        rejected = True

    assert_equal(True, rejected, "overlapping booking rejected")


def test_return_with_fine() -> None:
    app = CarRentalApp()
    seed_data(app)
    user = User("u1", "Satya", "satya@email.com")
    start = datetime(2026, 5, 20, 10, 0)
    end = datetime(2026, 5, 20, 15, 0)

    booking = app.controller.issue_car(user, "v1", start, end, PaymentMode.UPI)
    booking = app.controller.return_car(
        booking.booking_id,
        datetime(2026, 5, 20, 17, 0),
    )

    assert_equal(BookingStatus.COMPLETED, booking.status, "booking completed")
    assert_equal(100, booking.fine, "late return fine")


def test_concurrent_booking_only_one_wins() -> None:
    app = CarRentalApp()
    seed_data(app)
    user = User("u1", "Satya", "satya@email.com")
    start = datetime(2026, 5, 20, 10, 0)
    end = datetime(2026, 5, 20, 15, 0)
    results = []

    def issue() -> None:
        try:
            app.controller.issue_car(user, "v1", start, end, PaymentMode.UPI)
            results.append("SUCCESS")
        except BookingRejectedError:
            results.append("FAILED")

    t1 = Thread(target=issue)
    t2 = Thread(target=issue)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert_equal(["FAILED", "SUCCESS"], sorted(results), "only one concurrent booking wins")


def run_tests() -> None:
    test_search_and_issue_car()
    test_overlapping_booking_rejected()
    test_return_with_fine()
    test_concurrent_booking_only_one_wins()


def main() -> None:
    app = CarRentalApp()
    seed_data(app)
    user = User("u1", "Satya", "satya@email.com")
    start = datetime(2026, 5, 20, 10, 0)
    end = datetime(2026, 5, 20, 15, 0)

    available = app.controller.search_by_car_type(VehicleType.SEDAN, start, end)
    print("Available:", available)
    booking = app.controller.issue_car(user, available[0].vehicle_id, start, end, PaymentMode.UPI)
    print("Booking:", booking)

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
