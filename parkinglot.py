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


# =========================
# MODELS
# =========================

class Vehicle:
    def __init__(self, vehicle_type: VehicleType):
        self.id = str(uuid.uuid4())
        self.type = vehicle_type


class Spot:
    def __init__(self, spot_type: SpotType):
        self.id = str(uuid.uuid4())
        self.type = spot_type
        self.vehicle = None
        self.lock = threading.Lock()

    def is_free(self):
        return self.vehicle is None

    def can_fit(self, vehicle: Vehicle):
        # simple compatibility (no overengineering)
        if vehicle.type == VehicleType.BIKE:
            return True
        if vehicle.type == VehicleType.CAR:
            return self.type in [SpotType.MEDIUM, SpotType.LARGE]
        if vehicle.type == VehicleType.TRUCK:
            return self.type == SpotType.LARGE
        return False

    def park(self, vehicle: Vehicle):
        with self.lock:
            if not self.is_free() or not self.can_fit(vehicle):
                return False
            self.vehicle = vehicle
            return True

    def unpark(self):
        with self.lock:
            self.vehicle = None


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


# =========================
# STRATEGIES
# =========================

class AllocationStrategy(ABC):
    @abstractmethod
    def allocate(self, floors: list[Floor], vehicle: Vehicle) -> Spot:
        pass


class FirstAvailableStrategy(AllocationStrategy):
    def allocate(self, floors: list[Floor], vehicle: Vehicle):
        for floor in floors:
            for spot in floor.spots:
                if spot.park(vehicle):
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
        hours = math.ceil((end - start).total_seconds() / 3600)
        return hours * self.PRICES[vehicle.type]


# =========================
# PARKING LOT
# =========================

class ParkingLot:
    def __init__(self, floors: list[Floor],
                 allocation_strategy: AllocationStrategy,
                 pricing_strategy: PricingStrategy):

        self.floors = floors
        self.allocation_strategy = allocation_strategy
        self.pricing_strategy = pricing_strategy
        self.tickets = {}

    # -------- APIs --------

    def park(self, vehicle: Vehicle) -> Ticket:
        spot = self.allocation_strategy.allocate(self.floors, vehicle)

        if not spot:
            raise ValueError("No spot available")

        ticket = Ticket(spot, vehicle)
        self.tickets[ticket.id] = ticket
        return ticket

    def unpark(self, ticket_id: str):
        if ticket_id not in self.tickets:
            raise ValueError("Invalid ticket")

        ticket = self.tickets[ticket_id]
        ticket.end = datetime.datetime.now()

        ticket.spot.unpark()

        amount = self.pricing_strategy.calculate(
            ticket.start, ticket.end, ticket.vehicle
        )

        return {
            "vehicle_id": ticket.vehicle.id,
            "amount": amount
        }


# =========================
# HELPERS
# =========================

def create_floors(n):
    floors = []

    for i in range(n):
        floor = Floor(i + 1)

        # simple distribution
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
        floors,
        FirstAvailableStrategy(),
        HourlyPricingStrategy()
    )

    vehicle = Vehicle(VehicleType.BIKE)

    ticket = parking_lot.park(vehicle)
    print("Ticket:", ticket.id)

    import time
    time.sleep(2)

    print("Unpark:", parking_lot.unpark(ticket.id))


if __name__ == "__main__":
    main()