from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional, Set


class BookingStatus(Enum):
    CONFIRMED = "CONFIRMED"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class BookingRejectedError(Exception):
    pass


@dataclass
class VehicleInventory:
    count: int
    price_per_hour: int


@dataclass
class Branch:
    name: str
    inventory: Dict[str, VehicleInventory]
    lock: RLock = field(default_factory=RLock, repr=False)


@dataclass(frozen=True)
class Booking:
    booking_id: str
    branch_name: str
    vehicle_type: str
    start_time: datetime
    end_time: datetime
    price_per_hour: int
    status: BookingStatus = BookingStatus.CONFIRMED


class BranchRepository:
    def __init__(self):
        self.branches: Dict[str, Branch] = {}
        self.branches_by_vehicle_type: Dict[str, Set[str]] = {}
        self._lock = RLock()

    def create(self, branch: Branch) -> None:
        with self._lock:
            key = self._key(branch.name)
            if key in self.branches:
                raise ValidationError(f"Branch already exists: {branch.name}")
            self.branches[key] = branch
            for vehicle_type in branch.inventory:
                self.branches_by_vehicle_type.setdefault(vehicle_type, set()).add(key)

    def get(self, branch_name: str) -> Branch:
        with self._lock:
            branch = self.branches.get(self._key(branch_name))
            if not branch:
                raise NotFoundError(f"Branch not found: {branch_name}")
            return branch

    def list_all(self) -> List[Branch]:
        with self._lock:
            return list(self.branches.values())

    def list_by_vehicle_type(self, vehicle_type: str) -> List[Branch]:
        with self._lock:
            branch_names = self.branches_by_vehicle_type.get(vehicle_type, set())
            return [self.branches[name] for name in branch_names]

    def add_vehicle_type_index(
        self,
        branch_name: str,
        vehicle_type: str,
    ) -> None:
        with self._lock:
            self.branches_by_vehicle_type.setdefault(vehicle_type, set()).add(
                self._key(branch_name)
            )

    def _key(self, branch_name: str) -> str:
        return branch_name.strip().lower()


class BookingRepository:
    def __init__(self):
        self.bookings: Dict[str, Booking] = {}
        self.bookings_by_branch: Dict[str, List[Booking]] = {}
        self._lock = RLock()

    def save(self, booking: Booking) -> None:
        with self._lock:
            self.bookings[booking.booking_id] = booking
            branch_key = _normalize_name(booking.branch_name)
            self.bookings_by_branch.setdefault(branch_key, []).append(booking)

    def list_all(self) -> List[Booking]:
        with self._lock:
            return list(self.bookings.values())

    def list_by_branch(self, branch_name: str) -> List[Booking]:
        with self._lock:
            return list(self.bookings_by_branch.get(_normalize_name(branch_name), []))


class VehicleSelectionStrategy(ABC):
    @abstractmethod
    def select_branch(
        self,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
        branches: List[Branch],
        bookings_by_branch: Dict[str, List[Booking]],
    ) -> Optional[Branch]:
        pass


class LowestPriceSelectionStrategy(VehicleSelectionStrategy):
    def select_branch(
        self,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
        branches: List[Branch],
        bookings_by_branch: Dict[str, List[Booking]],
    ) -> Optional[Branch]:
        candidates = []
        for branch in branches:
            inventory = branch.inventory.get(vehicle_type)
            if not inventory:
                continue
            available_count = self._available_count(
                branch,
                vehicle_type,
                start_time,
                end_time,
                bookings_by_branch,
            )
            if available_count > 0:
                candidates.append(branch)

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda branch: (
                branch.inventory[vehicle_type].price_per_hour,
                branch.name,
            ),
        )

    def _available_count(
        self,
        branch: Branch,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
        bookings_by_branch: Dict[str, List[Booking]],
    ) -> int:
        inventory = branch.inventory[vehicle_type]
        booked_count = 0

        for booking in bookings_by_branch.get(_normalize_name(branch.name), []):
            if booking.vehicle_type != vehicle_type:
                continue
            if _overlaps(start_time, end_time, booking.start_time, booking.end_time):
                booked_count += 1

        return inventory.count - booked_count


class FlipKarRentalService:
    def __init__(
        self,
        branch_repo: BranchRepository,
        booking_repo: BookingRepository,
        selection_strategy: VehicleSelectionStrategy,
    ):
        self.branch_repo = branch_repo
        self.booking_repo = booking_repo
        self.selection_strategy = selection_strategy
        self._lock = RLock()
        self._next_booking_number = 1

    def add_branch(
        self,
        branch_name: str,
        inventory_by_type: Dict[str, tuple[int, int]],
    ) -> None:
        if not branch_name.strip():
            raise ValidationError("Branch name is required")
        if not inventory_by_type:
            raise ValidationError("Branch inventory is required")

        inventory = {}
        for vehicle_type, (count, price_per_hour) in inventory_by_type.items():
            self._validate_vehicle_input(vehicle_type, count, price_per_hour)
            inventory[self._normalize_vehicle_type(vehicle_type)] = VehicleInventory(
                count=count,
                price_per_hour=price_per_hour,
            )

        self.branch_repo.create(Branch(branch_name.strip(), inventory))

    def add_vehicle(
        self,
        branch_name: str,
        vehicle_type: str,
        count: int,
    ) -> None:
        if count <= 0:
            raise ValidationError("Vehicle count must be positive")

        vehicle_type = self._normalize_vehicle_type(vehicle_type)
        branch = self.branch_repo.get(branch_name)

        with branch.lock:
            inventory = branch.inventory.get(vehicle_type)
            if not inventory:
                raise ValidationError(
                    f"Vehicle type {vehicle_type} does not exist at {branch.name}"
                )
            inventory.count += count
            self.branch_repo.add_vehicle_type_index(branch.name, vehicle_type)

    def rent_vehicle(
        self,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
        now: Optional[datetime] = None,
    ) -> Booking:
        vehicle_type = self._normalize_vehicle_type(vehicle_type)
        self._validate_time_slot(start_time, end_time, now)

        with self._lock:
            branch = self.selection_strategy.select_branch(
                vehicle_type,
                start_time,
                end_time,
                self.branch_repo.list_by_vehicle_type(vehicle_type),
                self._bookings_by_branch_for_vehicle_type(vehicle_type),
            )
            if not branch:
                raise BookingRejectedError(f"No {vehicle_type} available")

            with branch.lock:
                if not self._is_available(branch, vehicle_type, start_time, end_time):
                    raise BookingRejectedError(f"No {vehicle_type} available")

                booking = Booking(
                    booking_id=self._next_booking_id_locked(),
                    branch_name=branch.name,
                    vehicle_type=vehicle_type,
                    start_time=start_time,
                    end_time=end_time,
                    price_per_hour=branch.inventory[vehicle_type].price_per_hour,
                )
                self.booking_repo.save(booking)
                return booking

    def system_view(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, List[str]]:
        self._validate_time_slot(start_time, end_time, now=None, check_future=False)
        view = {}

        for branch in self.branch_repo.list_all():
            rows = []
            with branch.lock:
                for vehicle_type, inventory in branch.inventory.items():
                    available_count = self._available_count(
                        branch,
                        vehicle_type,
                        start_time,
                        end_time,
                    )
                    if available_count <= 0:
                        rows.append(f'All "{vehicle_type}" are booked.')
                    else:
                        rows.append(
                            f'"{vehicle_type}" is available for Rs.{inventory.price_per_hour}'
                        )
            view[branch.name] = rows

        return view

    def print_system_view(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        for branch_name, rows in self.system_view(start_time, end_time).items():
            print(f"{branch_name}:")
            for row in rows:
                print(row)

    def _is_available(
        self,
        branch: Branch,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        return self._available_count(branch, vehicle_type, start_time, end_time) > 0

    def _available_count(
        self,
        branch: Branch,
        vehicle_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        inventory = branch.inventory[vehicle_type]
        booked_count = 0

        for booking in self.booking_repo.list_by_branch(branch.name):
            if booking.vehicle_type != vehicle_type:
                continue
            if _overlaps(start_time, end_time, booking.start_time, booking.end_time):
                booked_count += 1

        return inventory.count - booked_count

    def _bookings_by_branch_for_vehicle_type(
        self,
        vehicle_type: str,
    ) -> Dict[str, List[Booking]]:
        bookings_by_branch = {}
        for branch in self.branch_repo.list_by_vehicle_type(vehicle_type):
            bookings_by_branch[_normalize_name(branch.name)] = (
                self.booking_repo.list_by_branch(branch.name)
            )
        return bookings_by_branch

    def _validate_vehicle_input(
        self,
        vehicle_type: str,
        count: int,
        price_per_hour: int,
    ) -> None:
        if not vehicle_type.strip():
            raise ValidationError("Vehicle type is required")
        if count <= 0:
            raise ValidationError("Vehicle count must be positive")
        if price_per_hour <= 0:
            raise ValidationError("Vehicle price must be positive")

    def _validate_time_slot(
        self,
        start_time: datetime,
        end_time: datetime,
        now: Optional[datetime],
        check_future: bool = True,
    ) -> None:
        if end_time <= start_time:
            raise ValidationError("End time must be after start time")
        duration = end_time - start_time
        if duration.total_seconds() % 3600 != 0:
            raise ValidationError("Booking duration must be in full hours")
        if check_future and now is not None and now >= start_time:
            raise ValidationError("Booking must be made before start time")

    def _next_booking_id_locked(self) -> str:
        booking_id = f"Booking Id#{self._next_booking_number}"
        self._next_booking_number += 1
        return booking_id

    def _normalize_vehicle_type(self, vehicle_type: str) -> str:
        vehicle_type = vehicle_type.strip().lower()
        if vehicle_type.endswith("s"):
            return vehicle_type[:-1]
        return vehicle_type


class FlipKarRentalApp:
    def __init__(self):
        self.branch_repo = BranchRepository()
        self.booking_repo = BookingRepository()
        self.rental_service = FlipKarRentalService(
            self.branch_repo,
            self.booking_repo,
            LowestPriceSelectionStrategy(),
        )


def _overlaps(
    start_1: datetime,
    end_1: datetime,
    start_2: datetime,
    end_2: datetime,
) -> bool:
    return start_1 < end_2 and start_2 < end_1


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(app: FlipKarRentalApp) -> None:
    app.rental_service.add_branch(
        "Koramangala",
        {"suv": (1, 12), "sedan": (3, 10), "bike": (3, 20)},
    )
    app.rental_service.add_branch(
        "Jayanagar",
        {"sedan": (3, 11), "bike": (3, 30), "hatchback": (4, 8)},
    )
    app.rental_service.add_branch(
        "Malleshwaram",
        {"suv": (1, 11), "bike": (10, 3), "sedan": (3, 10)},
    )
    app.rental_service.add_vehicle("Koramangala", "sedan", 1)


def test_lowest_price_and_fallback() -> None:
    app = FlipKarRentalApp()
    seed_data(app)
    start = datetime(2027, 2, 20, 10)
    end = datetime(2027, 2, 20, 12)
    now = datetime(2027, 2, 19, 10)

    booking_1 = app.rental_service.rent_vehicle("suv", start, end, now=now)
    booking_2 = app.rental_service.rent_vehicle("suv", start, end, now=now)

    assert_equal("Malleshwaram", booking_1.branch_name, "cheapest suv selected")
    assert_equal("Koramangala", booking_2.branch_name, "fallback branch selected")


def test_no_vehicle_available() -> None:
    app = FlipKarRentalApp()
    seed_data(app)
    start = datetime(2027, 2, 20, 10)
    end = datetime(2027, 2, 20, 12)
    now = datetime(2027, 2, 19, 10)

    app.rental_service.rent_vehicle("suv", start, end, now=now)
    app.rental_service.rent_vehicle("suv", start, end, now=now)

    rejected = False
    try:
        app.rental_service.rent_vehicle("suv", start, end, now=now)
    except BookingRejectedError:
        rejected = True

    assert_equal(True, rejected, "third suv booking rejected")


def test_system_view() -> None:
    app = FlipKarRentalApp()
    seed_data(app)
    start = datetime(2027, 2, 20, 10)
    end = datetime(2027, 2, 20, 12)
    now = datetime(2027, 2, 19, 10)

    app.rental_service.rent_vehicle("suv", start, end, now=now)
    app.rental_service.rent_vehicle("suv", start, end, now=now)

    view = app.rental_service.system_view(
        datetime(2027, 2, 20, 11),
        datetime(2027, 2, 20, 12),
    )

    assert_equal(True, 'All "suv" are booked.' in view["Koramangala"], "koramangala suv blocked")
    assert_equal(True, 'All "suv" are booked.' in view["Malleshwaram"], "malleshwaram suv blocked")
    assert_equal(True, '"hatchback" is available for Rs.8' in view["Jayanagar"], "hatchback available")


def test_booking_must_be_before_start_time() -> None:
    app = FlipKarRentalApp()
    seed_data(app)
    start = datetime(2027, 2, 20, 10)
    end = datetime(2027, 2, 20, 12)

    rejected = False
    try:
        app.rental_service.rent_vehicle("bike", start, end, now=start)
    except ValidationError:
        rejected = True

    assert_equal(True, rejected, "booking at start time rejected")


def run_tests() -> None:
    test_lowest_price_and_fallback()
    test_no_vehicle_available()
    test_system_view()
    test_booking_must_be_before_start_time()


def main() -> None:
    app = FlipKarRentalApp()
    seed_data(app)
    start = datetime(2027, 2, 20, 10)
    end = datetime(2027, 2, 20, 12)
    now = datetime(2027, 2, 19, 10)

    print(app.rental_service.rent_vehicle("suv", start, end, now=now))
    print(app.rental_service.rent_vehicle("suv", start, end, now=now))

    try:
        app.rental_service.rent_vehicle("suv", start, end, now=now)
    except BookingRejectedError as error:
        print(error)

    app.rental_service.print_system_view(
        datetime(2027, 2, 20, 11),
        datetime(2027, 2, 20, 12),
    )

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
