"""
Flipkart Minutes – Quick Commerce System (P0 only)

Assumptions:
- Customer/partner IDs are provided at onboarding; order IDs are auto-generated (UUID).
- Item is a name string; all items always available.
- Assignment: background scheduler + Condition wake-up; FIFO queue.
- Cancel allowed only before pickup; frees partner if already assigned.
- Travel time ignored; partners available 24x7.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FlipkartMinutesError(Exception):
    pass


class EntityNotFoundError(FlipkartMinutesError):
    pass


class InvalidOperationError(FlipkartMinutesError):
    pass


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class OrderStatus(Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PartnerStatus(Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"


NON_CANCELLABLE = frozenset(
    {OrderStatus.PICKED_UP, OrderStatus.DELIVERED, OrderStatus.CANCELLED}
)


@dataclass
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
    status: OrderStatus = OrderStatus.CREATED
    partner_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def touch(self) -> None:
        self.updated_at = datetime.now()


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------


class CustomerRepository:
    def __init__(self) -> None:
        self._data: Dict[str, Customer] = {}

    def save(self, customer: Customer) -> None:
        if customer.customer_id in self._data:
            raise InvalidOperationError(
                f"Customer already exists: {customer.customer_id}"
            )
        self._data[customer.customer_id] = customer

    def get(self, customer_id: str) -> Customer:
        if customer_id not in self._data:
            raise EntityNotFoundError(f"Customer not found: {customer_id}")
        return self._data[customer_id]


class DeliveryPartnerRepository:
    def __init__(self) -> None:
        self._data: Dict[str, DeliveryPartner] = {}

    def save(self, partner: DeliveryPartner) -> None:
        if partner.partner_id in self._data:
            raise InvalidOperationError(
                f"Delivery partner already exists: {partner.partner_id}"
            )
        self._data[partner.partner_id] = partner

    def get(self, partner_id: str) -> DeliveryPartner:
        if partner_id not in self._data:
            raise EntityNotFoundError(
                f"Delivery partner not found: {partner_id}"
            )
        return self._data[partner_id]

    def all_available(self) -> List[DeliveryPartner]:
        return [
            p for p in self._data.values()
            if p.status == PartnerStatus.AVAILABLE
        ]


class OrderRepository:
    def __init__(self) -> None:
        self._data: Dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._data[order.order_id] = order

    def get(self, order_id: str) -> Order:
        if order_id not in self._data:
            raise EntityNotFoundError(f"Order not found: {order_id}")
        return self._data[order_id]

# ---------------------------------------------------------------------------
# Assignment scheduler (background thread + Condition)
# ---------------------------------------------------------------------------


class OrderAssignmentScheduler:
    """
    Daemon thread waits on a Condition until work exists, then assigns
    orders from the queue to available partners (FIFO).
    """

    def __init__(self, service: FlipkartMinutesService) -> None:
        self._service = service
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run, name="order-assigner", daemon=True
        )
        self._thread.start()

    def wake(self) -> None:
        with self._service._assign_cv:
            self._service._assign_cv.notify_all()

    def shutdown(self) -> None:
        with self._service._assign_cv:
            self._stopped = True
            self._service._assign_cv.notify_all()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            with self._service._assign_cv:
                if self._stopped:
                    return
                while self._service._process_assignment_round():
                    pass
                self._service._assign_cv.wait()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FlipkartMinutesService:
    def __init__(self) -> None:
        self._customers = CustomerRepository()
        self._partners = DeliveryPartnerRepository()
        self._orders = OrderRepository()
        self._pending_orders: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()
        self._assign_cv = threading.Condition(self._lock)
        self._scheduler = OrderAssignmentScheduler(self)

    def onboard_customer(self, customer_id: str, name: str) -> Customer:
        with self._lock:
            customer = Customer(customer_id=customer_id, name=name)
            self._customers.save(customer)
            return customer

    def onboard_delivery_partner(
        self, partner_id: str, name: str
    ) -> DeliveryPartner:
        with self._lock:
            partner = DeliveryPartner(partner_id=partner_id, name=name)
            self._partners.save(partner)
        self._scheduler.wake()
        return partner

    def create_order(self, customer_id: str, item_name: str) -> Order:
        with self._lock:
            self._customers.get(customer_id)
            if not item_name or not item_name.strip():
                raise InvalidOperationError("Item name cannot be empty")

            order = Order(
                order_id=str(uuid.uuid4()),
                customer_id=customer_id,
                item_name=item_name.strip(),
            )
            self._orders.save(order)
            self._pending_orders.put(order.order_id)
            self._scheduler.wake()
            self._wait_if_assignable(order)
            return order

    def cancel_order(self, order_id: str) -> Order:
        with self._lock:
            order = self._orders.get(order_id)
            if order.status in NON_CANCELLABLE:
                raise InvalidOperationError(
                    f"Cannot cancel order in status {order.status.value}"
                )

            order.status = OrderStatus.CANCELLED
            order.touch()

            partner_freed = bool(order.partner_id)
            if order.partner_id:
                self._release_partner(order.partner_id)

        self._scheduler.wake()
        if partner_freed:
            self._wait_for_assignable_work()
        return order

    def pick_up_order(self, partner_id: str, order_id: str) -> Order:
        with self._lock:
            partner = self._partners.get(partner_id)
            order = self._orders.get(order_id)

            if order.status != OrderStatus.ASSIGNED:
                raise InvalidOperationError(
                    f"Order {order_id} not ASSIGNED (current: {order.status.value})"
                )
            if order.partner_id != partner_id:
                raise InvalidOperationError(
                    f"Order {order_id} not assigned to {partner_id}"
                )
            if partner.status != PartnerStatus.BUSY:
                raise InvalidOperationError(f"Partner {partner_id} is not BUSY")

            order.status = OrderStatus.PICKED_UP
            order.touch()
            return order

    def complete_order(self, partner_id: str, order_id: str) -> Order:
        with self._lock:
            self._partners.get(partner_id)
            order = self._orders.get(order_id)

            if order.status != OrderStatus.PICKED_UP:
                raise InvalidOperationError(
                    f"Order {order_id} not PICKED_UP (current: {order.status.value})"
                )
            if order.partner_id != partner_id:
                raise InvalidOperationError(
                    f"Order {order_id} not assigned to {partner_id}"
                )

            order.status = OrderStatus.DELIVERED
            order.touch()
            self._release_partner(partner_id)

        self._scheduler.wake()
        self._wait_for_assignable_work()
        return order

    def show_order_status(self, order_id: str) -> OrderStatus:
        with self._lock:
            return self._orders.get(order_id).status

    def show_delivery_partner_status(self, partner_id: str) -> PartnerStatus:
        with self._lock:
            return self._partners.get(partner_id).status

    def shutdown(self) -> None:
        self._scheduler.shutdown()

    def _process_assignment_round(self) -> bool:
        """
        One assign or skip (stale/cancelled). Called under lock.
        Returns True if queue/partners should be rechecked immediately.
        """
        if not self._partners.all_available():
            return False

        try:
            order_id = self._pending_orders.get_nowait()
        except queue.Empty:
            return False

        order = self._orders.get(order_id)
        if order.status != OrderStatus.CREATED:
            return True  # drained a stale entry; keep going

        partner = self._partners.all_available()[0]
        order.status = OrderStatus.ASSIGNED
        order.partner_id = partner.partner_id
        order.touch()
        partner.status = PartnerStatus.BUSY
        partner.current_order_id = order.order_id
        return True

    def _wait_if_assignable(self, order: Order) -> None:
        """Block until scheduler assigns, or no partner left to assign."""
        with self._assign_cv:
            while (
                order.status == OrderStatus.CREATED
                and self._partners.all_available()
            ):
                self._assign_cv.wait(timeout=1.0)

    def _wait_for_assignable_work(self) -> None:
        """Block until pending queue is drained while partners are free."""
        with self._assign_cv:
            while (
                self._partners.all_available()
                and not self._pending_orders.empty()
            ):
                self._assign_cv.wait(timeout=1.0)

    def _release_partner(self, partner_id: str) -> None:
        partner = self._partners.get(partner_id)
        partner.status = PartnerStatus.AVAILABLE
        partner.current_order_id = None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _header(title: str) -> None:
    print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")


def main() -> None:
    svc = FlipkartMinutesService()

    _header("1. Onboarding")
    svc.onboard_customer("C1", "Alice")
    svc.onboard_customer("C2", "Bob")
    svc.onboard_delivery_partner("P1", "Ravi")
    svc.onboard_delivery_partner("P2", "Suresh")

    _header("2. Create orders + auto assign")
    o1 = svc.create_order("C1", "Milk")
    o2 = svc.create_order("C2", "Bread")
    o3 = svc.create_order("C1", "Eggs")
    print(f"{o1.order_id}={svc.show_order_status(o1.order_id).value}, P1={svc.show_delivery_partner_status('P1').value}")
    print(f"{o2.order_id}={svc.show_order_status(o2.order_id).value}, P2={svc.show_delivery_partner_status('P2').value}")
    print(f"{o3.order_id} (queued)={svc.show_order_status(o3.order_id).value}")

    _header("3. Cancel before pickup")
    svc.cancel_order(o1.order_id)
    print(f"{o1.order_id}={svc.show_order_status(o1.order_id).value}, P1={svc.show_delivery_partner_status('P1').value}")
    print(f"{o3.order_id} reassigned={svc.show_order_status(o3.order_id).value}")

    _header("4. Pickup + complete")
    svc.pick_up_order("P2", o2.order_id)
    try:
        svc.cancel_order(o2.order_id)
    except InvalidOperationError as e:
        print(f"Cancel after pickup blocked: {e}")
    svc.complete_order("P2", o2.order_id)
    print(f"{o2.order_id}={svc.show_order_status(o2.order_id).value}, P2={svc.show_delivery_partner_status('P2').value}")

    _header("5. Queue when partner busy")
    s2 = FlipkartMinutesService()
    s2.onboard_customer("C3", "Eve")
    s2.onboard_delivery_partner("P3", "Amit")
    o5 = s2.create_order("C3", "Rice")
    o6 = s2.create_order("C3", "Dal")
    print(f"{o5.order_id}={s2.show_order_status(o5.order_id).value}, {o6.order_id}={s2.show_order_status(o6.order_id).value}")
    s2.pick_up_order("P3", o5.order_id)
    print(f"{o6.order_id} while P3 busy={s2.show_order_status(o6.order_id).value}")
    s2.complete_order("P3", o5.order_id)
    print(f"{o6.order_id} after P3 free={s2.show_order_status(o6.order_id).value}")

    _header("6. Concurrent orders")
    s3 = FlipkartMinutesService()
    s3.onboard_customer("CX", "User")
    for i in range(3):
        s3.onboard_delivery_partner(f"PX{i}", f"Partner{i}")

    def place(n: int) -> None:
        s3.create_order("CX", f"Item-{n}")

    threads = [threading.Thread(target=place, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("10 concurrent orders placed OK")

    print("\nDone.")
    svc.shutdown()
    s2.shutdown()
    s3.shutdown()


if __name__ == "__main__":
    main()
