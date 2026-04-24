import uuid
from enum import Enum
from datetime import datetime
import math


# =========================
# ENUMS
# =========================

class VehicleType(Enum):
    CAR = 1
    BIKE = 2
    TRUCK = 3


class BookingStatus(Enum):
    CREATED = 1
    ACTIVE = 2
    COMPLETED = 3
    CANCELLED = 4


# =========================
# DOMAIN
# =========================

import threading

class Vehicle:
    def __init__(self, vehicle_id, v_type, base_price):
        self.id = vehicle_id
        self.type = v_type
        self.base_price = base_price
        self.bookings = []
        self.lock = threading.Lock()   # 🔥 important

class Booking:
    def __init__(self, vehicle_id, start, end):
        self.id = str(uuid.uuid4())
        self.vehicle_id = vehicle_id
        self.start_time = start
        self.end_time = end
        self.status = BookingStatus.CREATED

    def activate(self):
        if self.status != BookingStatus.CREATED:
            raise ValueError("Invalid transition")
        self.status = BookingStatus.ACTIVE

    def complete(self):
        if self.status != BookingStatus.ACTIVE:
            raise ValueError("Rental not active")
        self.status = BookingStatus.COMPLETED

    def cancel(self):
        if self.status != BookingStatus.CREATED:
            raise ValueError("Cannot cancel")
        self.status = BookingStatus.CANCELLED


# =========================
# SERVICES
# =========================

class AvailabilityService:
    def is_available(self, vehicle, start, end):
        for booking in vehicle.bookings:
            if booking.status == BookingStatus.CANCELLED:
                continue

            # overlap check
            if not (end <= booking.start_time or start >= booking.end_time):
                return False

        return True


class SearchService:
    def __init__(self, availability_service):
        self.availability = availability_service

    def search(self, vehicles, v_type, start, end):
        result = []

        for v in vehicles.values():
            if v.type != v_type:
                continue

            if self.availability.is_available(v, start, end):
                result.append(v)

        return result


# =========================
# PRICING STRATEGY
# =========================

class PricingStrategy:
    def calculate(self, vehicle, start, end):
        raise NotImplementedError


class HourlyPricing(PricingStrategy):
    def __init__(self, rate_map):
        self.rate_map = rate_map

    def calculate(self, vehicle, start, end):
        rate = self.rate_map.get(vehicle.type)

        duration_hours = (end - start).total_seconds() / 3600
        hours = math.ceil(duration_hours)

        return hours * rate


# =========================
# RENTAL SERVICE (ORCHESTRATOR)
# =========================

class RentalService:
    def __init__(self, pricing_strategy):
        self.vehicles = {}
        self.bookings = {}

        self.availability = AvailabilityService()
        self.search_service = SearchService(self.availability)

        self.pricing = pricing_strategy

    # ---------- VEHICLE ----------
    def add_vehicle(self, vehicle):
        self.vehicles[vehicle.id] = vehicle

    # ---------- SEARCH ----------
    def search(self, v_type, start, end):
        return self.search_service.search(
            self.vehicles, v_type, start, end
        )

    # ---------- BOOK ----------
    def book(self, vehicle_id, start, end):
        vehicle = self.vehicles.get(vehicle_id)

        if not vehicle:
            raise ValueError("Vehicle not found")

        # 🔥 acquire lock
        with vehicle.lock:

            # 🔥 re-check availability INSIDE lock
            if not self.availability.is_available(vehicle, start, end):
                raise ValueError("Vehicle unavailable")

            booking = Booking(vehicle_id, start, end)

            vehicle.bookings.append(booking)
            self.bookings[booking.id] = booking

            print(f"✅ Booked: {vehicle_id}")
            return booking

    # ---------- PICKUP ----------
    def pickup(self, booking_id):
        booking = self.bookings.get(booking_id)

        if not booking:
            raise ValueError("Invalid booking")

        booking.activate()
        print("🚗 Ride started")

    # ---------- RETURN ----------
    def return_vehicle(self, booking_id):
        booking = self.bookings.get(booking_id)

        if not booking:
            raise ValueError("Invalid booking")

        booking.complete()

        vehicle = self.vehicles.get(booking.vehicle_id)

        price = self.pricing.calculate(
            vehicle,
            booking.start_time,
            booking.end_time
        )

        print(f"💰 Price: {price}")
        return price

    # ---------- CANCEL ----------
    def cancel(self, booking_id):
        booking = self.bookings.get(booking_id)

        if not booking:
            raise ValueError("Invalid booking")

        booking.cancel()
        print("❌ Booking cancelled")


from datetime import datetime, timedelta


def main():
    # ---------- Setup ----------
    rate_map = {
        VehicleType.CAR: 100,
        VehicleType.BIKE: 50,
        VehicleType.TRUCK: 200
    }

    service = RentalService(HourlyPricing(rate_map))

    # add vehicles
    v1 = Vehicle("V1", VehicleType.CAR, 100)
    service.add_vehicle(v1)

    start = datetime.now()
    end = start + timedelta(hours=2)

    # ---------- Search ----------
    print("\n🔍 Searching vehicles...")
    results = service.search(VehicleType.CAR, start, end)
    print([v.id for v in results])

    # ---------- Concurrent Booking ----------
    print("\n⚡ Simulating concurrent booking...")

    def attempt_booking(user):
        try:
            booking = service.book("V1", start, end)
            print(f"{user} SUCCESS → BookingID: {booking.id}")
        except Exception as e:
            print(f"{user} FAILED → {e}")

    t1 = threading.Thread(target=attempt_booking, args=("User1",))
    t2 = threading.Thread(target=attempt_booking, args=("User2",))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # ---------- Pickup + Return ----------
    print("\n🚗 Completing booking...")

    # pick first successful booking
    booking_ids = list(service.bookings.keys())
    if booking_ids:
        booking_id = booking_ids[0]

        service.pickup(booking_id)

        # simulate trip end
        service.bookings[booking_id].end_time = datetime.now() + timedelta(hours=3)

        service.return_vehicle(booking_id)


if __name__ == "__main__":
    main()