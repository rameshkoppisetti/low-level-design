from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional


OK = "OK"
RESTAURANT_ALREADY_EXISTS = "RESTAURANT_ALREADY_EXISTS"
RESTAURANT_NOT_FOUND = "RESTAURANT_NOT_FOUND"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
INVALID_STRATEGY = "INVALID_STRATEGY"
DISPATCHED = "DISPATCHED"
INVALID_ORDER = "INVALID_ORDER"
ALREADY_DISPATCHED = "ALREADY_DISPATCHED"


class OrderStatus(Enum):
    ACCEPTED = "ACCEPTED"
    DISPATCHED = "DISPATCHED"


class CommandType(Enum):
    ADD_RESTAURANT = "ADD_RESTAURANT"
    UPDATE_MENU = "UPDATE_MENU"
    PLACE_ORDER = "PLACE_ORDER"
    DISPATCH_ORDER = "DISPATCH_ORDER"


class StrategyType(Enum):
    LOWEST_TOTAL_PRICE = "LOWEST_TOTAL_PRICE"
    MAX_REMAINING_CAPACITY = "MAX_REMAINING_CAPACITY"


@dataclass
class Restaurant:
    restaurant_id: str
    capacity: int
    menu: Dict[str, int]
    open_orders: int = 0
    served_items: Dict[str, int] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock, repr=False)

    def remaining_capacity(self) -> int:
        return self.capacity - self.open_orders

    def can_accept(self, items: List[str]) -> bool:
        return self.remaining_capacity() > 0 and all(item in self.menu for item in items)

    def total_price(self, items: List[str]) -> int:
        return sum(self.menu[item] for item in items)


@dataclass
class Order:
    order_id: str
    customer_id: str
    restaurant_id: str
    items: List[str]
    status: OrderStatus = OrderStatus.ACCEPTED
    dispatch_timestamp: Optional[int] = None
    lock: RLock = field(default_factory=RLock, repr=False)


class RestaurantRepository:
    def __init__(self):
        self.restaurants: Dict[str, Restaurant] = {}
        self._lock = RLock()

    def create(self, restaurant: Restaurant) -> bool:
        with self._lock:
            if restaurant.restaurant_id in self.restaurants:
                return False
            self.restaurants[restaurant.restaurant_id] = restaurant
            return True

    def get(self, restaurant_id: str) -> Optional[Restaurant]:
        with self._lock:
            return self.restaurants.get(restaurant_id)

    def list_all(self) -> List[Restaurant]:
        with self._lock:
            return list(self.restaurants.values())


class OrderRepository:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.dispatched_orders_by_restaurant: Dict[str, List[Order]] = {}
        self._lock = RLock()

    def create(self, order: Order) -> None:
        with self._lock:
            self.orders[order.order_id] = order

    def get(self, order_id: str) -> Optional[Order]:
        with self._lock:
            return self.orders.get(order_id)

    def add_dispatched(self, order: Order) -> None:
        with self._lock:
            self.dispatched_orders_by_restaurant.setdefault(
                order.restaurant_id,
                [],
            ).append(order)

    def list_dispatched(self, restaurant_id: str) -> List[Order]:
        with self._lock:
            return list(self.dispatched_orders_by_restaurant.get(restaurant_id, []))


class RestaurantSelectionStrategy:
    def rank(
        self,
        restaurants: List[Restaurant],
        items: List[str],
    ) -> List[Restaurant]:
        raise NotImplementedError


class LowestTotalPriceStrategy(RestaurantSelectionStrategy):
    def rank(
        self,
        restaurants: List[Restaurant],
        items: List[str],
    ) -> List[Restaurant]:
        candidates = [restaurant for restaurant in restaurants if restaurant.can_accept(items)]

        return sorted(
            candidates,
            key=lambda restaurant: (
                restaurant.total_price(items),
                -restaurant.remaining_capacity(),
                restaurant.restaurant_id,
            ),
        )


class MaxRemainingCapacityStrategy(RestaurantSelectionStrategy):
    def rank(
        self,
        restaurants: List[Restaurant],
        items: List[str],
    ) -> List[Restaurant]:
        candidates = [restaurant for restaurant in restaurants if restaurant.can_accept(items)]

        return sorted(
            candidates,
            key=lambda restaurant: (
                -restaurant.remaining_capacity(),
                restaurant.total_price(items),
                restaurant.restaurant_id,
            ),
        )


class RestaurantSelectionStrategyFactory:
    def __init__(self):
        self.strategies = {
            StrategyType.LOWEST_TOTAL_PRICE: LowestTotalPriceStrategy(),
            StrategyType.MAX_REMAINING_CAPACITY: MaxRemainingCapacityStrategy(),
        }

    def get(self, strategy_name: str) -> Optional[RestaurantSelectionStrategy]:
        try:
            strategy_type = StrategyType(strategy_name)
        except ValueError:
            return None
        return self.strategies.get(strategy_type)


class FoodCartService:
    def __init__(
        self,
        restaurant_repo: RestaurantRepository,
        order_repo: OrderRepository,
        strategy_factory: RestaurantSelectionStrategyFactory,
    ):
        self.restaurant_repo = restaurant_repo
        self.order_repo = order_repo
        self.strategy_factory = strategy_factory

    def add_restaurant(
        self,
        restaurant_id: str,
        capacity: int,
        menu: Dict[str, int],
    ) -> str:
        restaurant = Restaurant(restaurant_id, capacity, menu)
        if not self.restaurant_repo.create(restaurant):
            return RESTAURANT_ALREADY_EXISTS
        return OK

    def update_menu(self, restaurant_id: str, menu_updates: Dict[str, int]) -> str:
        restaurant = self.restaurant_repo.get(restaurant_id)
        if not restaurant:
            return RESTAURANT_NOT_FOUND

        with restaurant.lock:
            for item, price in menu_updates.items():
                if price < 0:
                    restaurant.menu.pop(item, None)
                else:
                    restaurant.menu[item] = price
        return OK

    def place_order(
        self,
        order_id: str,
        customer_id: str,
        strategy_name: str,
        items: List[str],
    ) -> str:
        strategy = self.strategy_factory.get(strategy_name)
        if not strategy:
            return INVALID_STRATEGY

        for restaurant in strategy.rank(self.restaurant_repo.list_all(), items):
            with restaurant.lock:
                if not restaurant.can_accept(items):
                    continue

                restaurant.open_orders += 1
                self.order_repo.create(
                    Order(
                        order_id=order_id,
                        customer_id=customer_id,
                        restaurant_id=restaurant.restaurant_id,
                        items=items,
                    )
                )
                return ACCEPTED

        return REJECTED

    def dispatch_order(self, order_id: str, timestamp: int) -> str:
        order = self.order_repo.get(order_id)
        if not order:
            return INVALID_ORDER

        restaurant = self.restaurant_repo.get(order.restaurant_id)
        if not restaurant:
            return INVALID_ORDER

        with order.lock:
            if order.status == OrderStatus.DISPATCHED:
                return ALREADY_DISPATCHED

            with restaurant.lock:
                if restaurant.open_orders > 0:
                    restaurant.open_orders -= 1
                for item in order.items:
                    restaurant.served_items[item] = restaurant.served_items.get(item, 0) + 1

                order.status = OrderStatus.DISPATCHED
                order.dispatch_timestamp = timestamp
                self.order_repo.add_dispatched(order)
                return DISPATCHED

    def get_restaurant_item_counts(self) -> List[str]:
        rows = []
        for restaurant in self.restaurant_repo.list_all():
            with restaurant.lock:
                for item, count in restaurant.served_items.items():
                    rows.append(f"{restaurant.restaurant_id}|{item}|{count}")
        return sorted(rows)

    def get_dispatched_orders(self, restaurant_id: str) -> List[str]:
        rows = []
        for order in self.order_repo.list_dispatched(restaurant_id):
            with order.lock:
                rows.append(
                    f"{order.dispatch_timestamp}|{order.order_id}|"
                    f"{order.customer_id}|{','.join(order.items)}"
                )
        return rows


class FoodCart:
    def __init__(self):
        self.restaurant_repo = RestaurantRepository()
        self.order_repo = OrderRepository()
        self.strategy_factory = RestaurantSelectionStrategyFactory()
        self.service = FoodCartService(
            self.restaurant_repo,
            self.order_repo,
            self.strategy_factory,
        )

    def processCommands(self, commands: List[str]) -> List[str]:
        outputs = [""] * len(commands)
        indexed_commands = []

        for index, command in enumerate(commands):
            timestamp = int(command.split("|", 1)[0])
            indexed_commands.append((timestamp, index, command))

        for _, original_index, command in sorted(indexed_commands, key=lambda item: (item[0], item[1])):
            outputs[original_index] = self._execute_command(command)

        return outputs

    def getRestaurantItemCounts(self) -> List[str]:
        return self.service.get_restaurant_item_counts()

    def getDispatchedOrders(self, restaurantId: str) -> List[str]:
        return self.service.get_dispatched_orders(restaurantId)

    def _execute_command(self, command: str) -> str:
        parts = command.split("|")
        timestamp = int(parts[0])
        try:
            command_type = CommandType(parts[1])
        except ValueError:
            return "INVALID_COMMAND"

        if command_type == CommandType.ADD_RESTAURANT:
            return self.service.add_restaurant(
                parts[2],
                int(parts[3]),
                _parse_menu(parts[4]),
            )

        if command_type == CommandType.UPDATE_MENU:
            return self.service.update_menu(parts[2], _parse_menu(parts[3]))

        if command_type == CommandType.PLACE_ORDER:
            return self.service.place_order(
                parts[2],
                parts[3],
                parts[4],
                _parse_items(parts[5]),
            )

        if command_type == CommandType.DISPATCH_ORDER:
            return self.service.dispatch_order(parts[2], timestamp)

        return "INVALID_COMMAND"


def _parse_menu(encoded_menu: str) -> Dict[str, int]:
    menu = {}
    if not encoded_menu:
        return menu

    for encoded_item in encoded_menu.split(","):
        item, price = encoded_item.split(":")
        menu[item] = int(price)
    return menu


def _parse_items(encoded_items: str) -> List[str]:
    if not encoded_items:
        return []
    return encoded_items.split(",")


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_sample_flow() -> None:
    food_cart = FoodCart()
    commands = [
        "200|PLACE_ORDER|O1|C1|LOWEST_TOTAL_PRICE|burger,pizza",
        "100|ADD_RESTAURANT|R1|2|burger:120,pizza:200",
        "150|ADD_RESTAURANT|R2|1|burger:110,pizza:220",
        "210|PLACE_ORDER|O2|C2|LOWEST_TOTAL_PRICE|burger",
        "220|DISPATCH_ORDER|O1",
        "205|UPDATE_MENU|R2|pizza:180",
        "230|PLACE_ORDER|O3|C3|LOWEST_TOTAL_PRICE|pizza",
    ]

    assert_equal(
        [
            "ACCEPTED",
            "OK",
            "OK",
            "ACCEPTED",
            "DISPATCHED",
            "OK",
            "ACCEPTED",
        ],
        food_cart.processCommands(commands),
        "sample outputs aligned to input order",
    )
    assert_equal(
        ["R1|burger|1", "R1|pizza|1"],
        food_cart.getRestaurantItemCounts(),
        "served item counts",
    )
    assert_equal(
        ["220|O1|C1|burger,pizza"],
        food_cart.getDispatchedOrders("R1"),
        "dispatched orders",
    )


def test_strategy_and_dispatch_failures() -> None:
    food_cart = FoodCart()
    outputs = food_cart.processCommands(
        [
            "1|ADD_RESTAURANT|R1|1|burger:100,pizza:200",
            "2|ADD_RESTAURANT|R2|3|burger:120,pizza:150",
            "3|PLACE_ORDER|O1|C1|BAD|burger",
            "4|PLACE_ORDER|O2|C2|MAX_REMAINING_CAPACITY|burger",
            "5|DISPATCH_ORDER|missing",
            "6|DISPATCH_ORDER|O2",
            "7|DISPATCH_ORDER|O2",
        ]
    )

    assert_equal(
        [
            "OK",
            "OK",
            "INVALID_STRATEGY",
            "ACCEPTED",
            "INVALID_ORDER",
            "DISPATCHED",
            "ALREADY_DISPATCHED",
        ],
        outputs,
        "strategy and dispatch failures",
    )


def run_tests() -> None:
    test_sample_flow()
    test_strategy_and_dispatch_failures()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
