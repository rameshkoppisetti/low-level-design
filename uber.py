import uuid
import math
from enum import Enum
from abc import ABC, abstractmethod
from typing import List, Optional


# =========================
# ENUMS
# =========================

class VehicleType(Enum):
    MINI = "MINI"
    SEDAN = "SEDAN"
    SUV = "SUV"


class RideStatus(Enum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# =========================
# DOMAIN
# =========================

class Location:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon


class User:
    def __init__(self, user_id: str, name: str):
        self.user_id = user_id
        self.name = name


class Rider(User):
    pass


class Vehicle:
    def __init__(self, vehicle_id: str, vehicle_type: VehicleType):
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type


import threading
# add this import


class Driver(User):
    def __init__(self, user_id: str, name: str, vehicle: Vehicle):
        super().__init__(user_id, name)
        self.vehicle = vehicle
        self.is_available = True
        self.location: Optional[Location] = None
        self._lock = threading.Lock()   # 🔥 NEW

    def update_location(self, location: Location):
        self.location = location

    # 🔥 ATOMIC ASSIGN
    def try_assign(self) -> bool:
        with self._lock:
            if not self.is_available:
                return False
            self.is_available = False
            return True

    def release(self):
        with self._lock:
            self.is_available = True


# =========================
# RIDE
# =========================

class Ride:
    def __init__(self, rider: Rider, source: Location, dest: Location, vehicle_type: VehicleType):
        self.id = str(uuid.uuid4())
        self.rider = rider
        self.driver: Optional[Driver] = None
        self.source = source
        self.destination = dest
        self.vehicle_type = vehicle_type
        self.status = RideStatus.REQUESTED
        self.fare = 0.0

    def assign_driver(self, driver: Driver):
        if self.status != RideStatus.REQUESTED:
            raise Exception("Invalid state transition")
        self.driver = driver
        self.status = RideStatus.ACCEPTED

    def start(self):
        if self.status != RideStatus.ACCEPTED:
            raise Exception("Ride not accepted")
        self.status = RideStatus.STARTED

    def complete(self):
        if self.status != RideStatus.STARTED:
            raise Exception("Ride not started")
        self.status = RideStatus.COMPLETED

    def cancel(self):
        self.status = RideStatus.CANCELLED


# =========================
# STRATEGIES
# =========================

class MatchingStrategy(ABC):
    @abstractmethod
    def match(self, drivers: List[Driver], source: Location) -> Optional[Driver]:
        pass


class NearestDriverStrategy(MatchingStrategy):
    def match(self, drivers: List[Driver], source: Location) -> Optional[Driver]:
        best = None
        min_dist = float("inf")

        for d in drivers:
            if not d.is_available or not d.location:
                continue

            dist = math.dist((d.location.lat, d.location.lon), (source.lat, source.lon))

            if dist < min_dist:
                min_dist = dist
                best = d

        return best


class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, ride: Ride) -> float:
        pass


class DefaultPricing(PricingStrategy):
    BASE = {
        VehicleType.MINI: 50,
        VehicleType.SEDAN: 80,
        VehicleType.SUV: 120
    }

    def calculate(self, ride: Ride) -> float:
        dist = math.dist(
            (ride.source.lat, ride.source.lon),
            (ride.destination.lat, ride.destination.lon)
        )
        return round(self.BASE[ride.vehicle_type] + dist * 10, 2)


# =========================
# SERVICES
# =========================

class DriverService:
    def __init__(self):
        self.drivers: List[Driver] = []

    def register_driver(self, driver: Driver, location: Location):
        driver.update_location(location)
        self.drivers.append(driver)

    def get_available(self, vehicle_type: VehicleType):
        return [
            d for d in self.drivers
            if d.is_available and d.vehicle.vehicle_type == vehicle_type
        ]
    


class RideService:
    def __init__(self, driver_service: DriverService,
                 matching: MatchingStrategy,
                 pricing: PricingStrategy):
        self.driver_service = driver_service
        self.matching = matching
        self.pricing = pricing
        self.rides = {}

    def request_ride(self, rider: Rider, src: Location, dest: Location, vehicle_type: VehicleType):
        ride = Ride(rider, src, dest, vehicle_type)

        drivers = self.driver_service.get_available(vehicle_type)

        # 🔥 iterate candidates instead of single pick
        for driver in sorted(
            drivers,
            key=lambda d: math.dist(
                (d.location.lat, d.location.lon),
                (src.lat, src.lon)
            )
        ):
            if driver.try_assign():   # 🔥 atomic check + assign
                ride.assign_driver(driver)
                self.rides[ride.id] = ride

                print(f"Driver {driver.name} assigned safely")
                return ride

        print("No drivers available (after contention)")
        return None

    def start_ride(self, ride_id):
        ride = self.rides.get(ride_id)
        ride.start()

    def complete_ride(self, ride_id):
        ride = self.rides.get(ride_id)

        ride.complete()
        ride.fare = self.pricing.calculate(ride)

        ride.driver.release()   # 🔥 thread-safe release

        print(f"Ride completed. Fare: ₹{ride.fare}")

    def cancel_ride(self, ride_id):
        ride = self.rides.get(ride_id)

        ride.cancel()
        if ride.driver:
            ride.driver.is_available = True


# =========================
# DEMO
# =========================

def main():
    driver_service = DriverService()

    d1 = Driver("d1", "Driver1", Vehicle("v1", VehicleType.MINI))
    d2 = Driver("d2", "Driver2", Vehicle("v2", VehicleType.SUV))

    driver_service.register_driver(d1, Location(0, 0))
    driver_service.register_driver(d2, Location(5, 5))

    ride_service = RideService(
        driver_service,
        NearestDriverStrategy(),
        DefaultPricing()
    )

    rider = Rider("r1", "Satya")

    ride = ride_service.request_ride(
        rider,
        Location(1, 1),
        Location(10, 10),
        VehicleType.SUV
    )

    if ride:
        ride_service.start_ride(ride.id)
        ride_service.complete_ride(ride.id)


if __name__ == "__main__":
    main()