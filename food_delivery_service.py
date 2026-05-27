from __future__ import annotations

import math
import threading
import uuid
from enum import IntEnum
from typing import Dict, List, Optional


class OrderStatus(IntEnum):
    PLACED = 0
    CONFIRMED = 1
    PREPARING = 2
    PICKED_UP = 3
    DELIVERED = 4


class Location:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon

    def distance_to(self, other: Location) -> float:
        return math.sqrt((self.lat - other.lat) ** 2 + (self.lon - other.lon) ** 2)


class Driver:
    def __init__(self, driver_id: str, name: str, rating: float, location: Location):
        self.id = driver_id
        self.name = name
        self.rating = rating
        self.location = location
        self.is_available = True
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            if not self.is_available:
                return False
            self.is_available = False
            return True

    def release(self) -> None:
        with self._lock:
            self.is_available = True


class OrderObserver:
    def on_order_status_changed(self, order_id: str, status: OrderStatus) -> None:
        raise NotImplementedError


class CustomerNotifier(OrderObserver):
    def on_order_status_changed(self, order_id: str, status: OrderStatus) -> None:
        print(f"[SMS to Customer] Order {order_id} is now {status.name}!")


class RestaurantNotifier(OrderObserver):
    def on_order_status_changed(self, order_id: str, status: OrderStatus) -> None:
        print(f"[Restaurant Alert] Order {order_id} moved to: {status.name}")


class Order:
    def __init__(self, order_id: str, restaurant_id: str, restaurant_location: Location):
        self.id = order_id
        self.restaurant_id = restaurant_id
        self.restaurant_location = restaurant_location
        self.status = OrderStatus.PLACED
        self.assigned_driver: Optional[Driver] = None
        self.observers: List[OrderObserver] = []
        self._lock = threading.RLock()

    def add_observer(self, observer: OrderObserver) -> None:
        with self._lock:
            self.observers.append(observer)

    def update_status(self, next_status: OrderStatus) -> bool:
        with self._lock:
            if next_status != self.status + 1:
                return False

            self.status = next_status
            observers = list(self.observers)

        for observer in observers:
            observer.on_order_status_changed(self.id, next_status)

        return True

    def assign_driver(self, driver: Driver) -> None:
        with self._lock:
            self.assigned_driver = driver


class DeliveryAssignmentStrategy:
    def rank_drivers(self, order: Order, drivers: List[Driver]) -> List[Driver]:
        raise NotImplementedError


class NearestDriverStrategy(DeliveryAssignmentStrategy):
    def rank_drivers(self, order: Order, drivers: List[Driver]) -> List[Driver]:
        return sorted(
            drivers,
            key=lambda driver: driver.location.distance_to(order.restaurant_location),
        )


class HighestRatedDriverStrategy(DeliveryAssignmentStrategy):
    def __init__(self, max_distance: float = 10.0):
        self.max_distance = max_distance

    def rank_drivers(self, order: Order, drivers: List[Driver]) -> List[Driver]:
        eligible = [
            driver
            for driver in drivers
            if driver.location.distance_to(order.restaurant_location) <= self.max_distance
        ]
        return sorted(eligible, key=lambda driver: driver.rating, reverse=True)


class FoodDeliveryService:
    def __init__(self, strategy: DeliveryAssignmentStrategy):
        self.strategy = strategy
        self.drivers: List[Driver] = []
        self.orders: Dict[str, Order] = {}
        self._lock = threading.RLock()

    def add_driver(self, driver: Driver) -> None:
        with self._lock:
            self.drivers.append(driver)

    def set_strategy(self, strategy: DeliveryAssignmentStrategy) -> None:
        with self._lock:
            self.strategy = strategy

    def place_order(self, restaurant_id: str, restaurant_location: Location) -> Order:
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order = Order(order_id, restaurant_id, restaurant_location)
        order.add_observer(CustomerNotifier())
        order.add_observer(RestaurantNotifier())

        with self._lock:
            self.orders[order_id] = order
            drivers_snapshot = list(self.drivers)
            strategy = self.strategy

        driver = self._assign_driver(order, drivers_snapshot, strategy)

        if driver:
            order.assign_driver(driver)
            order.update_status(OrderStatus.CONFIRMED)

        return order

    def update_order_status(self, order_id: str, next_status: OrderStatus) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False

        updated = order.update_status(next_status)

        if updated and next_status == OrderStatus.DELIVERED and order.assigned_driver:
            order.assigned_driver.release()

        return updated

    def _assign_driver(
        self,
        order: Order,
        drivers: List[Driver],
        strategy: DeliveryAssignmentStrategy,
    ) -> Optional[Driver]:
        ranked_drivers = strategy.rank_drivers(order, drivers)

        for driver in ranked_drivers:
            if driver.acquire():
                return driver

        return None


if __name__ == "__main__":
    service = FoodDeliveryService(NearestDriverStrategy())
    service.add_driver(Driver("DRV-01", "Bob", 4.2, Location(1.1, 1.1)))
    service.add_driver(Driver("DRV-02", "Alice", 4.9, Location(5.0, 5.0)))

    order_1 = service.place_order("PIZZA_HUB", Location(1.2, 1.2))
    print(
        "Assigned driver:",
        order_1.assigned_driver.name if order_1.assigned_driver else "NONE",
    )

    service.update_order_status(order_1.id, OrderStatus.PREPARING)
    service.update_order_status(order_1.id, OrderStatus.PICKED_UP)
    service.update_order_status(order_1.id, OrderStatus.DELIVERED)

    service.set_strategy(HighestRatedDriverStrategy())
    order_2 = service.place_order("BURGER_HOUSE", Location(4.8, 4.8))
    print(
        "Assigned driver:",
        order_2.assigned_driver.name if order_2.assigned_driver else "NONE",
    )
