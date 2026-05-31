from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Deque, Dict, List, Optional, Set


class OrderStatus(Enum):
    CREATED = "CREATED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"


class AgentStatus(Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


@dataclass
class Order:
    order_name: str
    pincode: str
    status: OrderStatus = OrderStatus.CREATED
    assigned_agent: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    delivery_minutes: Optional[int] = None


@dataclass
class DeliveryAgent:
    agent_name: str
    pincodes: Set[str]
    status: AgentStatus = AgentStatus.AVAILABLE


class OrderRepository:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.orders_by_pincode: Dict[str, Deque[str]] = defaultdict(deque)
        self._lock = RLock()

    def create(self, order: Order) -> None:
        with self._lock:
            key = self._key(order.order_name)
            if key in self.orders:
                raise ValidationError(f"Order already exists: {order.order_name}")
            self.orders[key] = order
            self.orders_by_pincode[order.pincode].append(key)

    def get(self, order_name: str) -> Order:
        with self._lock:
            order = self.orders.get(self._key(order_name))
            if not order:
                raise NotFoundError(f"Order not found: {order_name}")
            return order

    def pending_pincodes(self) -> List[str]:
        with self._lock:
            return list(self.orders_by_pincode.keys())

    def pop_next_pending(self, pincode: str) -> Optional[Order]:
        with self._lock:
            queue = self.orders_by_pincode.get(pincode)
            while queue:
                order = self.orders[queue.popleft()]
                if order.status == OrderStatus.CREATED:
                    return order
            return None

    def has_pending_orders(self) -> bool:
        with self._lock:
            for queue in self.orders_by_pincode.values():
                for order_name in queue:
                    if self.orders[order_name].status == OrderStatus.CREATED:
                        return True
            return False

    def _key(self, order_name: str) -> str:
        return order_name.strip().lower()


class AgentRepository:
    def __init__(self):
        self.agents: Dict[str, DeliveryAgent] = {}
        self.agents_by_pincode: Dict[str, Deque[str]] = defaultdict(deque)
        self._lock = RLock()

    def create(self, agent: DeliveryAgent) -> None:
        with self._lock:
            key = self._key(agent.agent_name)
            if key in self.agents:
                raise ValidationError(f"Agent already exists: {agent.agent_name}")
            self.agents[key] = agent
            for pincode in agent.pincodes:
                self.agents_by_pincode[pincode].append(key)

    def get(self, agent_name: str) -> DeliveryAgent:
        with self._lock:
            agent = self.agents.get(self._key(agent_name))
            if not agent:
                raise NotFoundError(f"Agent not found: {agent_name}")
            return agent

    def get_available_for_pincode(self, pincode: str) -> Optional[DeliveryAgent]:
        with self._lock:
            queue = self.agents_by_pincode.get(pincode)
            if not queue:
                return None

            for _ in range(len(queue)):
                agent_key = queue.popleft()
                agent = self.agents[agent_key]
                queue.append(agent_key)
                if agent.status == AgentStatus.AVAILABLE:
                    return agent

            return None

    def _key(self, agent_name: str) -> str:
        return agent_name.strip().lower()


class DeliveryService:
    def __init__(
        self,
        order_repo: OrderRepository,
        agent_repo: AgentRepository,
    ):
        self.order_repo = order_repo
        self.agent_repo = agent_repo
        self._lock = RLock()

    def create_order(
        self,
        order_name: str,
        pincode: str,
        scheduled_at: Optional[datetime] = None,
        delivery_minutes: Optional[int] = None,
    ) -> None:
        if not order_name.strip():
            raise ValidationError("Order name is required")
        if not pincode.strip():
            raise ValidationError("Pincode is required")
        if delivery_minutes is not None and delivery_minutes <= 0:
            raise ValidationError("Delivery minutes must be positive")

        order = Order(
            order_name=order_name.strip(),
            pincode=pincode.strip(),
            scheduled_at=scheduled_at,
            delivery_minutes=delivery_minutes,
        )
        self.order_repo.create(order)

    def create_agent(self, agent_name: str, pincodes: str | List[str]) -> None:
        if not agent_name.strip():
            raise ValidationError("Agent name is required")

        if isinstance(pincodes, str):
            pincode_set = {pincodes.strip()}
        else:
            pincode_set = {pincode.strip() for pincode in pincodes}

        if not pincode_set or any(not pincode for pincode in pincode_set):
            raise ValidationError("At least one pincode is required")

        self.agent_repo.create(DeliveryAgent(agent_name.strip(), pincode_set))

    def execute_deliveries(self) -> List[str]:
        logs = []

        with self._lock:
            made_progress = True
            while made_progress and self.order_repo.has_pending_orders():
                made_progress = False

                for pincode in self.order_repo.pending_pincodes():
                    agent = self.agent_repo.get_available_for_pincode(pincode)
                    if not agent:
                        continue

                    order = self.order_repo.pop_next_pending(pincode)
                    if not order:
                        continue

                    logs.extend(self._deliver_order(agent, order))
                    made_progress = True

        return logs

    def _deliver_order(
        self,
        agent: DeliveryAgent,
        order: Order,
    ) -> List[str]:
        agent.status = AgentStatus.BUSY
        order.status = OrderStatus.PICKED_UP
        order.assigned_agent = agent.agent_name

        if order.scheduled_at and order.delivery_minutes:
            pickup_time = _format_time(order.scheduled_at)
            delivery_time = _format_time(
                order.scheduled_at + timedelta(minutes=order.delivery_minutes)
            )
            logs = [
                f"{agent.agent_name} has picked up {order.order_name} at {pickup_time}",
                (
                    f"{agent.agent_name} has completed delivery of "
                    f"{order.order_name} to {order.pincode} at {delivery_time}"
                ),
            ]
        else:
            logs = [
                f"{agent.agent_name} has picked up {order.order_name}",
                f"{agent.agent_name} has delivered {order.order_name} to {order.pincode}",
            ]

        order.status = OrderStatus.DELIVERED
        agent.status = AgentStatus.AVAILABLE
        return logs


class DeliveryApp:
    def __init__(self):
        self.order_repo = OrderRepository()
        self.agent_repo = AgentRepository()
        self.delivery_service = DeliveryService(self.order_repo, self.agent_repo)


def _format_time(value: datetime) -> str:
    return value.strftime("%I:%M %p, %b %d, %Y").lstrip("0")


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_sample_flow() -> None:
    app = DeliveryApp()
    service = app.delivery_service

    service.create_order("Order A", "560087")
    service.create_order("Order B", "560088")
    service.create_order("Order C", "560089")
    service.create_order("Order D", "560087")
    service.create_agent("Agent A", "560087")
    service.create_agent("Agent B", "560088")
    service.create_agent("Agent C", "560089")

    assert_equal(
        [
            "Agent A has picked up Order A",
            "Agent A has delivered Order A to 560087",
            "Agent B has picked up Order B",
            "Agent B has delivered Order B to 560088",
            "Agent C has picked up Order C",
            "Agent C has delivered Order C to 560089",
            "Agent A has picked up Order D",
            "Agent A has delivered Order D to 560087",
        ],
        service.execute_deliveries(),
        "sample flow",
    )


def test_multi_pincode_agent() -> None:
    app = DeliveryApp()
    service = app.delivery_service

    service.create_order("Order A", "560087")
    service.create_order("Order B", "560088")
    service.create_agent("Agent A", ["560087", "560088"])

    logs = service.execute_deliveries()

    assert_equal("Agent A has picked up Order A", logs[0], "multi-pincode first order")
    assert_equal("Agent A has picked up Order B", logs[2], "multi-pincode second order")


def test_scheduled_delivery_logs_time() -> None:
    app = DeliveryApp()
    service = app.delivery_service
    scheduled_at = datetime(2025, 3, 22, 10, 30)

    service.create_order("Order A", "560087", scheduled_at, 30)
    service.create_agent("Agent A", "560087")

    assert_equal(
        [
            "Agent A has picked up Order A at 10:30 AM, Mar 22, 2025",
            (
                "Agent A has completed delivery of Order A "
                "to 560087 at 11:00 AM, Mar 22, 2025"
            ),
        ],
        service.execute_deliveries(),
        "scheduled delivery logs",
    )


def run_tests() -> None:
    test_sample_flow()
    test_multi_pincode_agent()
    test_scheduled_delivery_logs_time()


def main() -> None:
    app = DeliveryApp()
    service = app.delivery_service

    service.create_order("Order A", "560087")
    service.create_order("Order B", "560088")
    service.create_order("Order C", "560089")
    service.create_order("Order D", "560087")
    service.create_agent("Agent A", "560087")
    service.create_agent("Agent B", "560088")
    service.create_agent("Agent C", "560089")

    for log in service.execute_deliveries():
        print(log)

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
