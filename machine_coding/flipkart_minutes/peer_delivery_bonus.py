from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from time import time
from typing import Deque, Dict, List, Optional, Set, Tuple


class OrderStatus(Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"


class DriverStatus(Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    ON_DELIVERY = "ON_DELIVERY"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class InvalidStateError(Exception):
    pass


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str


@dataclass
class Driver:
    driver_id: str
    name: str
    status: DriverStatus = DriverStatus.AVAILABLE
    current_order_id: Optional[str] = None
    delivered_orders: int = 0
    rating_sum: int = 0
    rating_count: int = 0

    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return self.rating_sum / self.rating_count


@dataclass
class Order:
    order_id: str
    customer_id: str
    item_id: str
    status: OrderStatus = OrderStatus.QUEUED
    driver_id: Optional[str] = None
    created_at: float = 0.0


class CustomerRepository:
    def __init__(self):
        self.customers: Dict[str, Customer] = {}
        self._lock = RLock()

    def create(self, customer: Customer) -> None:
        with self._lock:
            if customer.customer_id in self.customers:
                raise ValidationError(f"Customer already exists: {customer.customer_id}")
            self.customers[customer.customer_id] = customer

    def get(self, customer_id: str) -> Customer:
        with self._lock:
            customer = self.customers.get(customer_id)
            if not customer:
                raise NotFoundError(f"Customer not found: {customer_id}")
            return customer


class DriverRepository:
    def __init__(self):
        self.drivers: Dict[str, Driver] = {}
        self._lock = RLock()

    def create(self, driver: Driver) -> None:
        with self._lock:
            if driver.driver_id in self.drivers:
                raise ValidationError(f"Driver already exists: {driver.driver_id}")
            self.drivers[driver.driver_id] = driver

    def get(self, driver_id: str) -> Driver:
        with self._lock:
            driver = self.drivers.get(driver_id)
            if not driver:
                raise NotFoundError(f"Driver not found: {driver_id}")
            return driver

    def list_all(self) -> List[Driver]:
        with self._lock:
            return list(self.drivers.values())


class OrderRepository:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self._lock = RLock()

    def save(self, order: Order) -> None:
        with self._lock:
            self.orders[order.order_id] = order

    def get(self, order_id: str) -> Order:
        with self._lock:
            order = self.orders.get(order_id)
            if not order:
                raise NotFoundError(f"Order not found: {order_id}")
            return order

    def list_all(self) -> List[Order]:
        with self._lock:
            return list(self.orders.values())


class NotificationVendor(ABC):
    @abstractmethod
    def send(self, recipient_id: str, message: str) -> None:
        pass


class EmailVendor(NotificationVendor):
    def send(self, recipient_id: str, message: str) -> None:
        print(f"[email:{recipient_id}] {message}")


class SmsVendor(NotificationVendor):
    def send(self, recipient_id: str, message: str) -> None:
        print(f"[sms:{recipient_id}] {message}")


class NotificationService:
    def __init__(self, vendors: List[NotificationVendor]):
        self.vendors = vendors

    def notify_customer(self, customer_id: str, message: str) -> None:
        for vendor in self.vendors:
            vendor.send(customer_id, message)

    def notify_driver(self, driver_id: str, message: str) -> None:
        for vendor in self.vendors:
            vendor.send(driver_id, message)


class DriverRankingStrategy(ABC):
    @abstractmethod
    def rank(self, drivers: List[Driver]) -> List[Driver]:
        pass


class DeliveryCountRankingStrategy(DriverRankingStrategy):
    def rank(self, drivers: List[Driver]) -> List[Driver]:
        return sorted(
            drivers,
            key=lambda driver: (-driver.delivered_orders, driver.driver_id),
        )


class RatingRankingStrategy(DriverRankingStrategy):
    def rank(self, drivers: List[Driver]) -> List[Driver]:
        return sorted(
            drivers,
            key=lambda driver: (-driver.average_rating(), -driver.delivered_orders, driver.driver_id),
        )


class PeerDeliveryService:
    AUTO_CANCEL_SECONDS = 30 * 60

    def __init__(
        self,
        customer_repo: CustomerRepository,
        driver_repo: DriverRepository,
        order_repo: OrderRepository,
        item_catalog: Set[str],
        notification_service: NotificationService,
    ):
        self.customer_repo = customer_repo
        self.driver_repo = driver_repo
        self.order_repo = order_repo
        self.item_catalog = {item.strip().lower() for item in item_catalog}
        self.notification_service = notification_service
        self.available_drivers: Deque[str] = deque()
        self.pending_orders: Deque[str] = deque()
        self._lock = RLock()
        self._next_order_number = 1

    def onboard_customer(self, customer_id: str, name: str) -> None:
        if not customer_id.strip() or not name.strip():
            raise ValidationError("Customer id and name are required")
        self.customer_repo.create(Customer(customer_id.strip(), name.strip()))

    def onboard_driver(self, driver_id: str, name: str) -> None:
        if not driver_id.strip() or not name.strip():
            raise ValidationError("Driver id and name are required")
        driver = Driver(driver_id.strip(), name.strip())
        self.driver_repo.create(driver)
        with self._lock:
            self.available_drivers.append(driver.driver_id)
            self._assign_orders_locked()

    def place_order(self, customer_id: str, item_id: str) -> Order:
        item_id = item_id.strip().lower()
        if not item_id:
            raise ValidationError("Item id is required")
        if item_id not in self.item_catalog:
            raise ValidationError(f"Item not supported: {item_id}")
        self.customer_repo.get(customer_id)

        with self._lock:
            order = Order(
                order_id=self._next_order_id_locked(),
                customer_id=customer_id,
                item_id=item_id,
                created_at=time(),
            )
            self.order_repo.save(order)
            self.pending_orders.append(order.order_id)
            self.notification_service.notify_customer(
                customer_id,
                f"Order {order.order_id} created",
            )
            self._assign_orders_locked()
            return order

    def cancel_order(self, order_id: str) -> None:
        with self._lock:
            order = self.order_repo.get(order_id)
            if order.status == OrderStatus.CANCELED:
                return
            if order.status == OrderStatus.DELIVERED:
                raise InvalidStateError("Cannot cancel delivered order")
            if order.status == OrderStatus.PICKED_UP:
                raise InvalidStateError("Cannot cancel order after pickup")

            driver_id = order.driver_id
            order.status = OrderStatus.CANCELED
            order.driver_id = None
            self.notification_service.notify_customer(
                order.customer_id,
                f"Order {order.order_id} canceled",
            )
            if driver_id:
                self.notification_service.notify_driver(
                    driver_id,
                    f"Order {order.order_id} canceled",
                )
                self._release_driver_locked(driver_id)
                self._assign_orders_locked()

    def pickup_order(self, driver_id: str, order_id: str) -> None:
        with self._lock:
            driver = self.driver_repo.get(driver_id)
            order = self.order_repo.get(order_id)

            if driver.current_order_id != order_id:
                raise InvalidStateError("Order is not assigned to this driver")
            if order.status != OrderStatus.ASSIGNED:
                raise InvalidStateError("Only assigned orders can be picked up")

            order.status = OrderStatus.PICKED_UP
            driver.status = DriverStatus.ON_DELIVERY
            self.notification_service.notify_customer(
                order.customer_id,
                f"Order {order.order_id} picked up",
            )

    def complete_order(self, driver_id: str, order_id: str) -> None:
        with self._lock:
            driver = self.driver_repo.get(driver_id)
            order = self.order_repo.get(order_id)

            if driver.current_order_id != order_id:
                raise InvalidStateError("Order is not assigned to this driver")
            if order.status != OrderStatus.PICKED_UP:
                raise InvalidStateError("Only picked-up orders can be delivered")

            order.status = OrderStatus.DELIVERED
            driver.delivered_orders += 1
            self.notification_service.notify_customer(
                order.customer_id,
                f"Order {order.order_id} delivered",
            )
            self._release_driver_locked(driver_id)
            self._assign_orders_locked()

    def rate_driver(self, customer_id: str, order_id: str, rating: int) -> None:
        if rating < 1 or rating > 5:
            raise ValidationError("Rating must be between 1 and 5")
        with self._lock:
            order = self.order_repo.get(order_id)
            if order.customer_id != customer_id:
                raise ValidationError("Customer did not create this order")
            if order.status != OrderStatus.DELIVERED:
                raise InvalidStateError("Only delivered orders can be rated")
            if not order.driver_id:
                raise InvalidStateError("Delivered order has no driver")

            driver = self.driver_repo.get(order.driver_id)
            driver.rating_sum += rating
            driver.rating_count += 1

    def auto_cancel_expired_orders(self, now: Optional[float] = None) -> None:
        current_time = now if now is not None else time()
        with self._lock:
            for order in self.order_repo.list_all():
                if order.status not in (OrderStatus.QUEUED, OrderStatus.ASSIGNED):
                    continue
                if current_time - order.created_at < self.AUTO_CANCEL_SECONDS:
                    continue

                driver_id = order.driver_id
                order.status = OrderStatus.CANCELED
                order.driver_id = None
                self.notification_service.notify_customer(
                    order.customer_id,
                    f"Order {order.order_id} auto-canceled",
                )
                if driver_id:
                    self.notification_service.notify_driver(
                        driver_id,
                        f"Order {order.order_id} auto-canceled",
                    )
                    self._release_driver_locked(driver_id)
            self._assign_orders_locked()

    def get_order_status(self, order_id: str) -> OrderStatus:
        return self.order_repo.get(order_id).status

    def get_driver_status(self, driver_id: str) -> DriverStatus:
        return self.driver_repo.get(driver_id).status

    def top_drivers(
        self,
        strategy: DriverRankingStrategy,
        limit: int = 3,
    ) -> List[Tuple[str, int, float]]:
        ranked = strategy.rank(self.driver_repo.list_all())
        return [
            (driver.driver_id, driver.delivered_orders, driver.average_rating())
            for driver in ranked[:limit]
        ]

    def _next_order_id_locked(self) -> str:
        order_id = f"Order Id#{self._next_order_number}"
        self._next_order_number += 1
        return order_id

    def _assign_orders_locked(self) -> None:
        while self.available_drivers and self.pending_orders:
            order_id = self.pending_orders.popleft()
            order = self.order_repo.get(order_id)
            if order.status != OrderStatus.QUEUED:
                continue

            driver_id = self.available_drivers.popleft()
            driver = self.driver_repo.get(driver_id)
            if driver.status != DriverStatus.AVAILABLE:
                self.pending_orders.appendleft(order_id)
                continue

            order.status = OrderStatus.ASSIGNED
            order.driver_id = driver_id
            driver.status = DriverStatus.ASSIGNED
            driver.current_order_id = order.order_id
            self.notification_service.notify_customer(
                order.customer_id,
                f"Order {order.order_id} assigned to driver {driver_id}",
            )
            self.notification_service.notify_driver(
                driver_id,
                f"Assigned order {order.order_id}",
            )

    def _release_driver_locked(self, driver_id: str) -> None:
        driver = self.driver_repo.get(driver_id)
        driver.status = DriverStatus.AVAILABLE
        driver.current_order_id = None
        self.available_drivers.append(driver_id)


class PeerDeliveryApp:
    def __init__(self):
        self.customer_repo = CustomerRepository()
        self.driver_repo = DriverRepository()
        self.order_repo = OrderRepository()
        self.notification_service = NotificationService([EmailVendor(), SmsVendor()])
        self.service = PeerDeliveryService(
            self.customer_repo,
            self.driver_repo,
            self.order_repo,
            {"documents", "food", "medicine"},
            self.notification_service,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(app: PeerDeliveryApp) -> None:
    app.service.onboard_customer("c1", "Anu")
    app.service.onboard_customer("c2", "Bala")
    app.service.onboard_driver("d1", "Driver One")


def test_assignment_queue_and_completion() -> None:
    app = PeerDeliveryApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "documents")
    order_2 = app.service.place_order("c2", "food")

    assert_equal(OrderStatus.ASSIGNED, order_1.status, "first order assigned")
    assert_equal(OrderStatus.QUEUED, order_2.status, "second order queued")

    app.service.pickup_order("d1", order_1.order_id)
    app.service.complete_order("d1", order_1.order_id)

    assert_equal(OrderStatus.ASSIGNED, order_2.status, "queued order assigned")


def test_cancel_assigned_order_releases_driver() -> None:
    app = PeerDeliveryApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "documents")
    order_2 = app.service.place_order("c2", "food")
    app.service.cancel_order(order_1.order_id)

    assert_equal(OrderStatus.CANCELED, order_1.status, "order canceled")
    assert_equal(OrderStatus.ASSIGNED, order_2.status, "driver reassigned")


def test_cannot_cancel_after_pickup() -> None:
    app = PeerDeliveryApp()
    seed_data(app)

    order = app.service.place_order("c1", "documents")
    app.service.pickup_order("d1", order.order_id)

    rejected = False
    try:
        app.service.cancel_order(order.order_id)
    except InvalidStateError:
        rejected = True

    assert_equal(True, rejected, "cancel after pickup rejected")


def test_rating_dashboard_and_auto_cancel() -> None:
    app = PeerDeliveryApp()
    seed_data(app)

    order = app.service.place_order("c1", "documents")
    app.service.pickup_order("d1", order.order_id)
    app.service.complete_order("d1", order.order_id)
    app.service.rate_driver("c1", order.order_id, 5)

    assert_equal(
        [("d1", 1, 5.0)],
        app.service.top_drivers(RatingRankingStrategy()),
        "rating dashboard",
    )

    queued_order = app.service.place_order("c2", "food")
    app.service.auto_cancel_expired_orders(
        now=queued_order.created_at + PeerDeliveryService.AUTO_CANCEL_SECONDS + 1
    )
    assert_equal(OrderStatus.CANCELED, queued_order.status, "expired order canceled")


def run_tests() -> None:
    test_assignment_queue_and_completion()
    test_cancel_assigned_order_releases_driver()
    test_cannot_cancel_after_pickup()
    test_rating_dashboard_and_auto_cancel()


def main() -> None:
    app = PeerDeliveryApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "documents")
    order_2 = app.service.place_order("c2", "food")
    print(order_1)
    print(order_2)
    print(app.service.get_order_status(order_1.order_id))
    print(app.service.get_driver_status("d1"))

    app.service.pickup_order("d1", order_1.order_id)
    app.service.complete_order("d1", order_1.order_id)
    app.service.rate_driver("c1", order_1.order_id, 5)
    print(app.service.top_drivers(DeliveryCountRankingStrategy()))

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
