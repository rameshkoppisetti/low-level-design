from abc import ABC, abstractmethod
from queue import Empty, Queue
import datetime
import enum
import uuid
import threading
import math


# =========================
# ENUMS
# =========================

class VehicleType(enum.Enum):
    CAR = 1
    BIKE = 2
    TRUCK = 3


# =========================
# DOMAIN
# =========================

class Vehicle:
    def __init__(self, vehicle_type):
        self.id = str(uuid.uuid4())
        self.type = vehicle_type


class Slot:
    def __init__(self, vehicle_type):
        self.id = str(uuid.uuid4())
        self.type = vehicle_type
        self.available = True
        self.vehicle = None
        self.lock = threading.Lock()

    def park(self, vehicle):
        with self.lock:
            if not self.available:
                return False

            if self.type != vehicle.type:
                return False

            self.vehicle = vehicle
            self.available = False
            return True

    def unpark(self):
        with self.lock:
            vehicle = self.vehicle
            self.vehicle = None
            self.available = True
            return vehicle


class Floor:
    def __init__(self, number, slots):
        self.number = number
        self.slots = slots


class Ticket:
    def __init__(self, vehicle_id, slot):
        self.id = str(uuid.uuid4())
        self.vehicle_id = vehicle_id
        self.start = datetime.datetime.now()
        self.end = None
        self.slot = slot


# =========================
# STRATEGIES
# =========================

class AllocationStrategy(ABC):
    @abstractmethod
    def allocate(self, parking_lot, vehicle):
        pass


class O1AllocationStrategy(AllocationStrategy):
    def allocate(self, parking_lot, vehicle):
        queue = parking_lot.free_slots[vehicle.type]

        try:
            return queue.get_nowait()
        except Empty:
            return None


class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, start, end, vehicle_type):
        pass


PRICES_MAP = {
    VehicleType.BIKE: 10,
    VehicleType.CAR: 30,
    VehicleType.TRUCK: 40
}


class BasePricingStrategy(PricingStrategy):
    def calculate(self, start, end, vehicle_type):
        hours = (end - start).total_seconds() / 3600
        rate = PRICES_MAP.get(vehicle_type)
        return max(1, math.ceil(hours)) * rate


# =========================
# PARKING LOT
# =========================

class ParkingLot:
    def __init__(self, floors, allocation_strategy, pricing_strategy):
        self.floors = floors
        self.allocation_strategy = allocation_strategy
        self.pricing_strategy = pricing_strategy
        self.tickets = {}

        # O(1) free slot index
        self.free_slots = {
            VehicleType.BIKE: Queue(),
            VehicleType.CAR: Queue(),
            VehicleType.TRUCK: Queue()
        }
        self.ticket_lock = threading.Lock()

        self._initialize_free_slots()

    def _initialize_free_slots(self):
        for floor in self.floors:
            for slot in floor.slots:
                self.free_slots[slot.type].put(slot)

    # ---------- PARK ----------
    def park(self, vehicle):
        slot = self.allocation_strategy.allocate(self, vehicle)

        if not slot:
            raise ValueError("No slot available")

        if not slot.park(vehicle):
            raise ValueError("Slot booking failed")

        ticket = Ticket(vehicle.id, slot)

        with self.ticket_lock:
            self.tickets[ticket.id] = ticket

        return ticket

    # ---------- UNPARK ----------
    def unpark(self, ticket_id):
        with self.ticket_lock:
            if ticket_id not in self.tickets:
                raise ValueError("Invalid ticket")

            ticket = self.tickets.pop(ticket_id)

        ticket.end = datetime.datetime.now()

        slot = ticket.slot
        vehicle = slot.unpark()

        if vehicle is None:
            raise ValueError("Slot already empty")

        self.free_slots[vehicle.type].put(slot)

        duration = (ticket.end - ticket.start).total_seconds() / 3600

        price = self.pricing_strategy.calculate(
            ticket.start,
            ticket.end,
            vehicle.type
        )

        return {
            "vehicle_id": vehicle.id,
            "price": price,
            "duration_hours": round(duration, 2)
        }

    # ---------- AVAILABLE ----------
    def available_slots_per_floor(self, vehicle_type):
        result = {}

        for floor in self.floors:
            count = 0
            for slot in floor.slots:
                if slot.available and slot.type == vehicle_type:
                    count += 1
            result[floor.number] = count

        return result

    # ---------- GET TICKET ----------
    def get_ticket_details(self, ticket_id):
        with self.ticket_lock:
            return self.tickets.get(ticket_id)


# =========================
# SETUP
# =========================

def create_floors(n):
    floors = []

    for i in range(n):
        slots = []
        slots += [Slot(VehicleType.BIKE) for _ in range(3)]
        slots += [Slot(VehicleType.CAR) for _ in range(3)]
        slots += [Slot(VehicleType.TRUCK) for _ in range(2)]

        floors.append(Floor(i, slots))

    return floors


# =========================
# MAIN
# =========================

def main():
    floors = create_floors(3)

    parking_lot = ParkingLot(
        floors,
        O1AllocationStrategy(),
        BasePricingStrategy()
    )

    vehicle = Vehicle(VehicleType.CAR)

    # park
    ticket = parking_lot.park(vehicle)
    print("Ticket:", ticket.id)

    # unpark
    result = parking_lot.unpark(ticket.id)
    print("Unpark:", result)

    # availability
    print("Available:", parking_lot.available_slots_per_floor(VehicleType.CAR))


if __name__ == "__main__":
    main()