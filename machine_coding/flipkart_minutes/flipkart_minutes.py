from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Deque, Dict, Optional


class OrderStatus(Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"


class PartnerStatus(Enum):
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
class DeliveryPartner:
    partner_id: str
    name: str
    status: PartnerStatus = PartnerStatus.AVAILABLE
    current_order_id: Optional[str] = None


@dataclass
class Order:
    order_id: str
    customer_id: str
    item_name: str
    status: OrderStatus = OrderStatus.QUEUED
    partner_id: Optional[str] = None


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


class PartnerRepository:
    def __init__(self):
        self.partners: Dict[str, DeliveryPartner] = {}
        self._lock = RLock()

    def create(self, partner: DeliveryPartner) -> None:
        with self._lock:
            if partner.partner_id in self.partners:
                raise ValidationError(f"Partner already exists: {partner.partner_id}")
            self.partners[partner.partner_id] = partner

    def get(self, partner_id: str) -> DeliveryPartner:
        with self._lock:
            partner = self.partners.get(partner_id)
            if not partner:
                raise NotFoundError(f"Partner not found: {partner_id}")
            return partner

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


class FlipkartMinutesService:
    def __init__(
        self,
        customer_repo: CustomerRepository,
        partner_repo: PartnerRepository,
        order_repo: OrderRepository,
    ):
        self.customer_repo = customer_repo
        self.partner_repo = partner_repo
        self.order_repo = order_repo
        self.available_partners: Deque[str] = deque()
        self.pending_orders: Deque[str] = deque()
        self._lock = RLock()
        self._next_order_number = 1

    def onboard_customer(self, customer_id: str, name: str) -> None:
        if not customer_id.strip() or not name.strip():
            raise ValidationError("Customer id and name are required")
        self.customer_repo.create(Customer(customer_id.strip(), name.strip()))

    def onboard_delivery_partner(self, partner_id: str, name: str) -> None:
        if not partner_id.strip() or not name.strip():
            raise ValidationError("Partner id and name are required")
        partner = DeliveryPartner(partner_id.strip(), name.strip())
        self.partner_repo.create(partner)
        with self._lock:
            self.available_partners.append(partner.partner_id)
            self._assign_orders_locked()

    def place_order(self, customer_id: str, item_name: str) -> Order:
        if not item_name.strip():
            raise ValidationError("Item name is required")
        self.customer_repo.get(customer_id)

        with self._lock:
            order = Order(
                order_id=self._next_order_id_locked(),
                customer_id=customer_id,
                item_name=item_name.strip(),
            )
            self.order_repo.save(order)
            self.pending_orders.append(order.order_id)
            self._assign_orders_locked()
            return order

    def cancel_order(self, order_id: str) -> None:
        with self._lock:
            order = self.order_repo.get(order_id)
            if order.status == OrderStatus.CANCELED:
                return
            if order.status == OrderStatus.DELIVERED:
                raise InvalidStateError(f"Cannot cancel {order.status.value} order")
            if order.status == OrderStatus.PICKED_UP:
                raise InvalidStateError("Cannot cancel order after pickup")

            partner_id = order.partner_id
            order.status = OrderStatus.CANCELED
            order.partner_id = None

            if partner_id:
                self._release_partner_locked(partner_id)
                self._assign_orders_locked()

    def pickup_order(self, partner_id: str, order_id: str) -> None:
        with self._lock:
            partner = self.partner_repo.get(partner_id)
            order = self.order_repo.get(order_id)

            if partner.current_order_id != order_id:
                raise InvalidStateError("Order is not assigned to this partner")
            if order.status != OrderStatus.ASSIGNED:
                raise InvalidStateError("Only assigned orders can be picked up")

            order.status = OrderStatus.PICKED_UP
            partner.status = PartnerStatus.ON_DELIVERY

    def complete_order(self, partner_id: str, order_id: str) -> None:
        with self._lock:
            partner = self.partner_repo.get(partner_id)
            order = self.order_repo.get(order_id)

            if partner.current_order_id != order_id:
                raise InvalidStateError("Order is not assigned to this partner")
            if order.status != OrderStatus.PICKED_UP:
                raise InvalidStateError("Only picked-up orders can be delivered")

            order.status = OrderStatus.DELIVERED
            self._release_partner_locked(partner_id)
            self._assign_orders_locked()

    def get_order_status(self, order_id: str) -> OrderStatus:
        return self.order_repo.get(order_id).status

    def get_delivery_partner_status(self, partner_id: str) -> PartnerStatus:
        return self.partner_repo.get(partner_id).status

    def _next_order_id_locked(self) -> str:
        order_id = f"Order Id#{self._next_order_number}"
        self._next_order_number += 1
        return order_id

    def _assign_orders_locked(self) -> None:
        while self.available_partners and self.pending_orders:
            order_id = self.pending_orders.popleft()
            order = self.order_repo.get(order_id)
            if order.status != OrderStatus.QUEUED:
                continue

            partner_id = self.available_partners.popleft()
            partner = self.partner_repo.get(partner_id)
            if partner.status != PartnerStatus.AVAILABLE:
                self.pending_orders.appendleft(order_id)
                continue

            order.status = OrderStatus.ASSIGNED
            order.partner_id = partner_id
            partner.status = PartnerStatus.ASSIGNED
            partner.current_order_id = order.order_id

    def _release_partner_locked(self, partner_id: str) -> None:
        partner = self.partner_repo.get(partner_id)
        partner.status = PartnerStatus.AVAILABLE
        partner.current_order_id = None
        self.available_partners.append(partner_id)


class FlipkartMinutesApp:
    def __init__(self):
        self.customer_repo = CustomerRepository()
        self.partner_repo = PartnerRepository()
        self.order_repo = OrderRepository()
        self.service = FlipkartMinutesService(
            self.customer_repo,
            self.partner_repo,
            self.order_repo,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(app: FlipkartMinutesApp) -> None:
    app.service.onboard_customer("c1", "Anu")
    app.service.onboard_customer("c2", "Bala")
    app.service.onboard_delivery_partner("p1", "Partner One")


def test_assignment_and_queue() -> None:
    app = FlipkartMinutesApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "Milk")
    order_2 = app.service.place_order("c2", "Bread")

    assert_equal(OrderStatus.ASSIGNED, order_1.status, "first order assigned")
    assert_equal(OrderStatus.QUEUED, order_2.status, "second order queued")

    app.service.pickup_order("p1", order_1.order_id)
    app.service.complete_order("p1", order_1.order_id)

    assert_equal(OrderStatus.ASSIGNED, order_2.status, "queued order assigned later")


def test_cancel_before_pickup_releases_partner() -> None:
    app = FlipkartMinutesApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "Milk")
    order_2 = app.service.place_order("c2", "Bread")

    app.service.cancel_order(order_1.order_id)

    assert_equal(OrderStatus.CANCELED, order_1.status, "assigned order canceled")
    assert_equal(OrderStatus.ASSIGNED, order_2.status, "partner reassigned after cancel")


def test_cancel_is_idempotent() -> None:
    app = FlipkartMinutesApp()
    seed_data(app)

    order = app.service.place_order("c1", "Milk")
    app.service.cancel_order(order.order_id)
    app.service.cancel_order(order.order_id)

    assert_equal(OrderStatus.CANCELED, order.status, "cancel is idempotent")


def test_cannot_cancel_after_pickup() -> None:
    app = FlipkartMinutesApp()
    seed_data(app)

    order = app.service.place_order("c1", "Milk")
    app.service.pickup_order("p1", order.order_id)

    rejected = False
    try:
        app.service.cancel_order(order.order_id)
    except InvalidStateError:
        rejected = True

    assert_equal(True, rejected, "cannot cancel after pickup")


def test_wrong_partner_cannot_pickup() -> None:
    app = FlipkartMinutesApp()

    app.service.onboard_customer("c1", "Anu")
    app.service.onboard_delivery_partner("p1", "Partner One")
    app.service.onboard_delivery_partner("p2", "Partner Two")

    order = app.service.place_order("c1", "Milk")

    rejected = False
    try:
        app.service.pickup_order("p2", order.order_id)
    except InvalidStateError:
        rejected = True

    assert_equal(True, rejected, "wrong partner cannot pickup order")


def test_multiple_orders_with_two_partners() -> None:
    app = FlipkartMinutesApp()

    app.service.onboard_customer("c1", "Anu")
    app.service.onboard_delivery_partner("p1", "Partner One")
    app.service.onboard_delivery_partner("p2", "Partner Two")

    order_1 = app.service.place_order("c1", "Milk")
    order_2 = app.service.place_order("c1", "Bread")
    order_3 = app.service.place_order("c1", "Eggs")

    assert_equal(OrderStatus.ASSIGNED, order_1.status, "order 1 assigned")
    assert_equal(OrderStatus.ASSIGNED, order_2.status, "order 2 assigned")
    assert_equal(OrderStatus.QUEUED, order_3.status, "order 3 queued")


def run_tests() -> None:
    test_assignment_and_queue()
    test_cancel_before_pickup_releases_partner()
    test_cancel_is_idempotent()
    test_cannot_cancel_after_pickup()
    test_wrong_partner_cannot_pickup()
    test_multiple_orders_with_two_partners()


def main() -> None:
    app = FlipkartMinutesApp()
    seed_data(app)

    order_1 = app.service.place_order("c1", "Milk")
    order_2 = app.service.place_order("c2", "Bread")

    print(order_1)
    print(order_2)
    print(app.service.get_order_status(order_1.order_id))
    print(app.service.get_delivery_partner_status("p1"))

    app.service.pickup_order("p1", order_1.order_id)
    app.service.complete_order("p1", order_1.order_id)

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
