from abc import ABC, abstractmethod
from enum import Enum
import datetime
import math
import threading
import uuid


# =========================
# ENUMS
# =========================

class VehicleType(Enum):
    BIKE = 1
    CAR = 2
    TRUCK = 3


class SpotType(Enum):
    SMALL = 1
    MEDIUM = 2
    LARGE = 3


class TicketStatus(Enum):
    ACTIVE = 1
    CLOSED = 2


# =========================
# MODELS
# =========================

class Vehicle:
    def __init__(self, vehicle_type: VehicleType, number: str):
        self.id = str(uuid.uuid4())
        self.type = vehicle_type
        self.number = number


class Spot:
    def __init__(self, spot_type: SpotType):
        self.id = str(uuid.uuid4())
        self.type = spot_type
        self.vehicle = None
        self.lock = threading.Lock()

    def is_free(self):
        return self.vehicle is None

    def can_fit(self, vehicle: Vehicle):
        if vehicle.type == VehicleType.BIKE:
            return self.type in [SpotType.SMALL, SpotType.MEDIUM, SpotType.LARGE]

        if vehicle.type == VehicleType.CAR:
            return self.type in [SpotType.MEDIUM, SpotType.LARGE]

        if vehicle.type == VehicleType.TRUCK:
            return self.type == SpotType.LARGE

        return False

    def try_park(self, vehicle: Vehicle):
        """
        Non-blocking parking.

        If another thread is currently checking/parking this spot,
        we do not wait. We immediately return False and caller can
        move to next spot.
        """
        acquired = self.lock.acquire(blocking=False)

        if not acquired:
            return False

        try:
            if not self.is_free():
                return False

            if not self.can_fit(vehicle):
                return False

            self.vehicle = vehicle
            return True

        finally:
            self.lock.release()

    def unpark(self):
        with self.lock:
            if self.vehicle is None:
                return None

            vehicle = self.vehicle
            self.vehicle = None
            return vehicle


class Floor:
    def __init__(self, floor_id: int):
        self.id = floor_id
        self.spots = []


class Ticket:
    def __init__(self, spot: Spot, vehicle: Vehicle):
        self.id = str(uuid.uuid4())
        self.spot = spot
        self.vehicle = vehicle
        self.start = datetime.datetime.now()
        self.end = None
        self.status = TicketStatus.ACTIVE


# =========================
# STRATEGIES
# =========================

class AllocationStrategy(ABC):
    @abstractmethod
    def allocate(self, floors: list[Floor], vehicle: Vehicle) -> Spot | None:
        pass


class BestFitAllocationStrategy(AllocationStrategy):
    def allocate(self, floors: list[Floor], vehicle: Vehicle) -> Spot | None:
        preferred_spot_order = {
            VehicleType.BIKE: [SpotType.SMALL, SpotType.MEDIUM, SpotType.LARGE],
            VehicleType.CAR: [SpotType.MEDIUM, SpotType.LARGE],
            VehicleType.TRUCK: [SpotType.LARGE],
        }

        for spot_type in preferred_spot_order[vehicle.type]:
            for floor in floors:
                for spot in floor.spots:
                    if spot.type == spot_type and spot.try_park(vehicle):
                        return spot

        return None


class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, start, end, vehicle: Vehicle):
        pass


class HourlyPricingStrategy(PricingStrategy):
    PRICES = {
        VehicleType.BIKE: 10,
        VehicleType.CAR: 20,
        VehicleType.TRUCK: 30,
    }

    def calculate(self, start, end, vehicle: Vehicle):
        seconds = (end - start).total_seconds()
        hours = math.ceil(seconds / 3600)

        # minimum 1 hour charge
        hours = max(1, hours)

        return hours * self.PRICES[vehicle.type]


# =========================
# PARKING LOT
# =========================

class ParkingLot:
    def __init__(
        self,
        floors: list[Floor],
        allocation_strategy: AllocationStrategy,
        pricing_strategy: PricingStrategy
    ):
        self.floors = floors
        self.allocation_strategy = allocation_strategy
        self.pricing_strategy = pricing_strategy

        self.tickets = {}
        self.active_vehicle_ticket = {}

        self.ticket_lock = threading.Lock()

    def park(self, vehicle: Vehicle) -> Ticket:
        # First check if same vehicle is already parked
        with self.ticket_lock:
            if vehicle.number in self.active_vehicle_ticket:
                raise ValueError("Vehicle already parked")

        # Allocation internally uses non-blocking spot lock
        spot = self.allocation_strategy.allocate(self.floors, vehicle)

        if spot is None:
            raise ValueError("No spot available")

        ticket = Ticket(spot, vehicle)

        with self.ticket_lock:
            self.tickets[ticket.id] = ticket
            self.active_vehicle_ticket[vehicle.number] = ticket.id

        return ticket

    def unpark(self, ticket_id: str):
        with self.ticket_lock:
            if ticket_id not in self.tickets:
                raise ValueError("Invalid ticket")

            ticket = self.tickets[ticket_id]

            if ticket.status != TicketStatus.ACTIVE:
                raise ValueError("Ticket already closed")

        ticket.end = datetime.datetime.now()

        vehicle = ticket.spot.unpark()

        if vehicle is None:
            raise ValueError("Spot already empty")

        if vehicle.id != ticket.vehicle.id:
            raise ValueError("Vehicle mismatch")

        amount = self.pricing_strategy.calculate(
            ticket.start,
            ticket.end,
            ticket.vehicle
        )

        with self.ticket_lock:
            ticket.status = TicketStatus.CLOSED
            self.active_vehicle_ticket.pop(ticket.vehicle.number, None)

        return {
            "ticket_id": ticket.id,
            "vehicle_id": ticket.vehicle.id,
            "vehicle_number": ticket.vehicle.number,
            "amount": amount
        }


# =========================
# HELPERS
# =========================

def create_floors(n):
    floors = []

    for i in range(n):
        floor = Floor(i + 1)

        floor.spots += [Spot(SpotType.SMALL) for _ in range(3)]
        floor.spots += [Spot(SpotType.MEDIUM) for _ in range(3)]
        floor.spots += [Spot(SpotType.LARGE) for _ in range(2)]

        floors.append(floor)

    return floors


# =========================
# DEMO
# =========================

def main():
    floors = create_floors(3)

    parking_lot = ParkingLot(
        floors=floors,
        allocation_strategy=BestFitAllocationStrategy(),
        pricing_strategy=HourlyPricingStrategy()
    )

    vehicle1 = Vehicle(VehicleType.BIKE, "KA-01-BIKE-1234")
    vehicle2 = Vehicle(VehicleType.CAR, "KA-01-CAR-9999")

    ticket1 = parking_lot.park(vehicle1)
    print("Ticket 1:", ticket1.id)

    ticket2 = parking_lot.park(vehicle2)
    print("Ticket 2:", ticket2.id)

    print("Unpark 1:", parking_lot.unpark(ticket1.id))
    print("Unpark 2:", parking_lot.unpark(ticket2.id))


if __name__ == "__main__":
    main()