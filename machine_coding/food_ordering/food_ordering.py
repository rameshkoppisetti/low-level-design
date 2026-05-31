from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import DefaultDict, Dict, List, Optional, Set


class OrderStatus(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FULFILLED = "FULFILLED"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class OrderRejectedError(Exception):
    pass


@dataclass
class Restaurant:
    name: str
    menu: Dict[str, int]
    max_capacity: int
    in_flight_items: int = 0
    served_items: Dict[str, int] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock, repr=False)

    def remaining_capacity(self) -> int:
        return self.max_capacity - self.in_flight_items

    def can_accept(self, count: int) -> bool:
        return self.remaining_capacity() >= count

    def reserve_items(self, items: List[str]) -> None:
        if not self.can_accept(len(items)):
            raise OrderRejectedError(f"Restaurant capacity full: {self.name}")

        self.in_flight_items += len(items)
        for item in items:
            key = item.strip().lower()
            self.served_items[key] = self.served_items.get(key, 0) + 1

    def release_items(self, count: int) -> None:
        if count > self.in_flight_items:
            raise ValidationError("Cannot release more items than in-flight")
        self.in_flight_items -= count


@dataclass(frozen=True)
class OrderAssignment:
    item_name: str
    restaurant_name: str
    price: int


@dataclass
class Order:
    order_id: str
    assignments: List[OrderAssignment]
    status: OrderStatus = OrderStatus.ACCEPTED

    def restaurants(self) -> List[str]:
        return sorted({assignment.restaurant_name for assignment in self.assignments})


class RestaurantRepository:
    def __init__(self):
        self.restaurants: Dict[str, Restaurant] = {}
        self.restaurants_by_item: DefaultDict[str, Set[str]] = defaultdict(set)
        self._lock = RLock()

    def create(self, restaurant: Restaurant) -> None:
        with self._lock:
            key = self._key(restaurant.name)
            if key in self.restaurants:
                raise ValidationError(f"Restaurant already exists: {restaurant.name}")
            self.restaurants[key] = restaurant
            self._add_to_item_index(restaurant)

    def get(self, restaurant_name: str) -> Restaurant:
        with self._lock:
            restaurant = self.restaurants.get(self._key(restaurant_name))
            if not restaurant:
                raise NotFoundError(f"Restaurant not found: {restaurant_name}")
            return restaurant

    def list_all(self) -> Dict[str, Restaurant]:
        with self._lock:
            return {
                restaurant.name: restaurant
                for restaurant in self.restaurants.values()
            }

    def list_by_item(self) -> Dict[str, Set[str]]:
        with self._lock:
            return {
                item: set(restaurant_names)
                for item, restaurant_names in self.restaurants_by_item.items()
            }

    def replace_menu(
        self,
        restaurant_name: str,
        menu: Dict[str, int],
        capacity: Optional[int],
    ) -> None:
        restaurant = self.get(restaurant_name)
        normalized_menu = self._normalize_menu(menu)

        with restaurant.lock:
            if capacity is not None:
                if capacity <= 0:
                    raise ValidationError("Capacity must be positive")
                if restaurant.in_flight_items > capacity:
                    raise ValidationError("New capacity is lower than in-flight item count")
                restaurant.max_capacity = capacity

            with self._lock:
                self._remove_from_item_index(restaurant.name, restaurant.menu)
                restaurant.menu = normalized_menu
                self._add_to_item_index(restaurant)

    def _key(self, restaurant_name: str) -> str:
        return restaurant_name.strip().lower()

    def _add_to_item_index(self, restaurant: Restaurant) -> None:
        for item in restaurant.menu:
            self.restaurants_by_item[item].add(restaurant.name)

    def _remove_from_item_index(
        self,
        restaurant_name: str,
        menu: Dict[str, int],
    ) -> None:
        for item in menu:
            restaurant_names = self.restaurants_by_item.get(item)
            if not restaurant_names:
                continue

            restaurant_names.discard(restaurant_name)
            if not restaurant_names:
                del self.restaurants_by_item[item]

    def _normalize_menu(self, menu: Dict[str, int]) -> Dict[str, int]:
        if not menu:
            raise ValidationError("Menu cannot be empty")

        normalized = {}
        for item_name, price in menu.items():
            if not item_name.strip():
                raise ValidationError("Item name cannot be empty")
            if price <= 0:
                raise ValidationError("Item price must be positive")
            normalized[item_name.strip().lower()] = price
        return normalized


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


class RestaurantSelectionStrategy(ABC):
    @abstractmethod
    def select(
        self,
        items: List[str],
        restaurants_by_name: Dict[str, Restaurant],
        restaurants_by_item: Dict[str, Set[str]],
    ) -> Optional[List[OrderAssignment]]:
        pass


class LowestPriceSelectionStrategy(RestaurantSelectionStrategy):
    def select(
        self,
        items: List[str],
        restaurants_by_name: Dict[str, Restaurant],
        restaurants_by_item: Dict[str, Set[str]],
    ) -> Optional[List[OrderAssignment]]:
        normalized_items = [item.strip().lower() for item in items]
        if any(not restaurants_by_item.get(item) for item in normalized_items):
            return None

        candidate_restaurant_names = set()
        for item in normalized_items:
            candidate_restaurant_names.update(restaurants_by_item.get(item, set()))

        remaining_capacity = {
            name: restaurants_by_name[name].remaining_capacity()
            for name in candidate_restaurant_names
        }

        ordered_items = sorted(
            normalized_items,
            key=lambda item: (
                len(restaurants_by_item.get(item, set())),
                min(
                    restaurants_by_name[name].menu[item]
                    for name in restaurants_by_item.get(item, set())
                ),
                item,
            ),
        )

        assignments: List[OrderAssignment] = []
        best_assignments: Optional[List[OrderAssignment]] = None
        best_total: Optional[int] = None

        def backtrack(index: int, total_price: int) -> None:
            nonlocal best_assignments, best_total

            if best_total is not None and total_price >= best_total:
                return

            if index == len(ordered_items):
                best_total = total_price
                best_assignments = list(assignments)
                return

            item = ordered_items[index]
            candidate_names = sorted(
                restaurants_by_item.get(item, set()),
                key=lambda name: (restaurants_by_name[name].menu[item], name),
            )

            for restaurant_name in candidate_names:
                if remaining_capacity[restaurant_name] <= 0:
                    continue

                restaurant = restaurants_by_name[restaurant_name]
                price = restaurant.menu[item]
                remaining_capacity[restaurant_name] -= 1
                assignments.append(OrderAssignment(item, restaurant_name, price))

                backtrack(index + 1, total_price + price)

                assignments.pop()
                remaining_capacity[restaurant_name] += 1

        backtrack(0, 0)

        return best_assignments


class RestaurantService:
    def __init__(self, restaurant_repo: RestaurantRepository):
        self.restaurant_repo = restaurant_repo

    def add_restaurant(
        self,
        name: str,
        menu: Dict[str, int],
        capacity: int,
    ) -> None:
        if not name.strip():
            raise ValidationError("Restaurant name cannot be empty")
        if capacity <= 0:
            raise ValidationError("Capacity must be positive")

        normalized_menu = self.restaurant_repo._normalize_menu(menu)
        restaurant = Restaurant(
            name=name.strip(),
            menu=normalized_menu,
            max_capacity=capacity,
        )
        self.restaurant_repo.create(restaurant)

    def change_menu(
        self,
        restaurant_name: str,
        menu: Dict[str, int],
        capacity: Optional[int] = None,
    ) -> None:
        self.restaurant_repo.replace_menu(
            restaurant_name,
            menu,
            capacity,
        )


class OrderService:
    def __init__(
        self,
        restaurant_repo: RestaurantRepository,
        order_repo: OrderRepository,
        selection_strategy: RestaurantSelectionStrategy,
    ):
        self.restaurant_repo = restaurant_repo
        self.order_repo = order_repo
        self.selection_strategy = selection_strategy
        self._order_id_lock = RLock()
        self._next_order_number = 1

    def place_order(self, items: List[str]) -> Order:
        self._validate_items(items)

        restaurants_by_name = self.restaurant_repo.list_all()
        restaurants_by_item = self.restaurant_repo.list_by_item()
        assignments = self.selection_strategy.select(
            items,
            restaurants_by_name,
            restaurants_by_item,
        )

        if not assignments:
            raise OrderRejectedError("Order cannot be fulfilled")

        grouped_items = self._group_items_by_restaurant(assignments)
        selected_restaurants = [
            restaurants_by_name[name]
            for name in sorted(grouped_items)
        ]

        for restaurant in selected_restaurants:
            restaurant.lock.acquire()

        try:
            if not self._can_still_fulfill(grouped_items, restaurants_by_name):
                raise OrderRejectedError("Order cannot be fulfilled")

            for restaurant_name, items in grouped_items.items():
                restaurants_by_name[restaurant_name].reserve_items(items)

            order = Order(
                order_id=self._next_order_id(),
                assignments=assignments,
            )
            self.order_repo.save(order)
            return order
        finally:
            for restaurant in reversed(selected_restaurants):
                restaurant.lock.release()

    def fulfill_order(self, order_id: str) -> None:
        order = self.order_repo.get(order_id)

        if order.status == OrderStatus.FULFILLED:
            raise ValidationError("Order already fulfilled")
        if order.status != OrderStatus.ACCEPTED:
            raise ValidationError("Only accepted orders can be fulfilled")

        restaurants_by_name = self.restaurant_repo.list_all()
        grouped_items = self._group_items_by_restaurant(order.assignments)
        selected_restaurants = [
            restaurants_by_name[name]
            for name in sorted(grouped_items)
        ]

        for restaurant in selected_restaurants:
            restaurant.lock.acquire()

        try:
            for restaurant_name, items in grouped_items.items():
                restaurants_by_name[restaurant_name].release_items(len(items))
            order.status = OrderStatus.FULFILLED
        finally:
            for restaurant in reversed(selected_restaurants):
                restaurant.lock.release()

    def _validate_items(self, items: List[str]) -> None:
        if not items:
            raise ValidationError("Order must contain at least one item")
        if any(not item.strip() for item in items):
            raise ValidationError("Item name cannot be empty")

    def _next_order_id(self) -> str:
        with self._order_id_lock:
            order_id = f"Order Id#{self._next_order_number}"
            self._next_order_number += 1
            return order_id

    def _can_still_fulfill(
        self,
        grouped_items: Dict[str, List[str]],
        restaurants_by_name: Dict[str, Restaurant],
    ) -> bool:
        for restaurant_name, items in grouped_items.items():
            restaurant = restaurants_by_name[restaurant_name]
            if not restaurant.can_accept(len(items)):
                return False
            for item in items:
                if item not in restaurant.menu:
                    return False

        return True

    def _group_items_by_restaurant(
        self,
        assignments: List[OrderAssignment],
    ) -> Dict[str, List[str]]:
        grouped_items: Dict[str, List[str]] = {}

        for assignment in assignments:
            grouped_items.setdefault(assignment.restaurant_name, []).append(
                assignment.item_name
            )

        return grouped_items


class StatsService:
    def __init__(self, restaurant_repo: RestaurantRepository):
        self.restaurant_repo = restaurant_repo

    def print_stats(self) -> Dict[str, int]:
        stats = {}

        for restaurant in self.restaurant_repo.list_all().values():
            with restaurant.lock:
                stats[restaurant.name] = restaurant.remaining_capacity()

        return stats

    def served_items(self) -> Dict[str, Dict[str, int]]:
        stats = {}

        for restaurant in self.restaurant_repo.list_all().values():
            with restaurant.lock:
                stats[restaurant.name] = dict(restaurant.served_items)

        return stats


class FoodOrderingApp:
    def __init__(self):
        self.restaurant_repo = RestaurantRepository()
        self.order_repo = OrderRepository()
        self.restaurant_service = RestaurantService(self.restaurant_repo)
        self.order_service = OrderService(
            self.restaurant_repo,
            self.order_repo,
            LowestPriceSelectionStrategy(),
        )
        self.stats_service = StatsService(self.restaurant_repo)


def format_order(order: Order) -> str:
    restaurants = ' & '.join(f'"{name}"' for name in order.restaurants())
    return f"{order.order_id}: Ordered from {restaurants}"


def seed_data(app: FoodOrderingApp) -> None:
    app.restaurant_service.add_restaurant(
        "A2B",
        {"Idly": 40, "Vada": 30, "Paper Plain Dosa": 50},
        4,
    )
    app.restaurant_service.add_restaurant(
        "Rasaganga",
        {"Idly": 45, "Set Dosa": 60, "Poori": 25},
        6,
    )
    app.restaurant_service.add_restaurant(
        "Eat Fit",
        {"Idly": 30, "Vada": 40},
        2,
    )


def print_stats(stats: Dict[str, int]) -> None:
    for restaurant_name, capacity in stats.items():
        print(f"{restaurant_name}: {capacity}")


def assert_equal(expected, actual, msg: str) -> None:
    if expected != actual:
        raise AssertionError(f"{msg}: expected={expected}, actual={actual}")
    print(f"PASSED: {msg}")


def test_sample_flow() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    order_1 = app.order_service.place_order(["Idly", "Poori"])
    assert_equal(
        'Order Id#1: Ordered from "Eat Fit" & "Rasaganga"',
        format_order(order_1),
        "sample order 1",
    )

    order_2 = app.order_service.place_order(["Idly", "Vada"])
    assert_equal(
        'Order Id#2: Ordered from "A2B" & "Eat Fit"',
        format_order(order_2),
        "sample order 2",
    )


def test_unavailable_item_rejected() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    rejected = False
    try:
        app.order_service.place_order(["Pizza"])
    except OrderRejectedError:
        rejected = True

    assert_equal(True, rejected, "unavailable item should be rejected")


def test_capacity_fallback() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    app.order_service.place_order(["Idly"])
    app.order_service.place_order(["Idly"])
    order = app.order_service.place_order(["Idly"])

    assert_equal(
        'Order Id#3: Ordered from "A2B"',
        format_order(order),
        "capacity fallback should pick next cheapest restaurant",
    )


def test_fulfillment_releases_capacity() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    order = app.order_service.place_order(["Idly"])

    assert_equal(
        1,
        app.stats_service.print_stats()["Eat Fit"],
        "capacity should reduce after order",
    )

    app.order_service.fulfill_order(order.order_id)

    assert_equal(
        2,
        app.stats_service.print_stats()["Eat Fit"],
        "capacity should release after fulfillment",
    )


def test_greedy_failure_case() -> None:
    app = FoodOrderingApp()

    app.restaurant_service.add_restaurant("R1", {"Idly": 10, "Vada": 10}, 1)
    app.restaurant_service.add_restaurant("R2", {"Idly": 11}, 1)

    order = app.order_service.place_order(["Idly", "Vada"])

    assert_equal(
        'Order Id#1: Ordered from "R1" & "R2"',
        format_order(order),
        "backtracking should find valid allocation where greedy fails",
    )


def run_quick_tests() -> None:
    test_sample_flow()
    test_unavailable_item_rejected()
    test_capacity_fallback()
    test_fulfillment_releases_capacity()
    test_greedy_failure_case()


def main() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    order_1 = app.order_service.place_order(["Idly", "Poori"])
    print(format_order(order_1))

    order_2 = app.order_service.place_order(["Idly", "Vada"])
    print(format_order(order_2))

    print("Stats after two orders:")
    print_stats(app.stats_service.print_stats())

    order_3 = app.order_service.place_order(["Idly"])
    print(format_order(order_3))

    app.order_service.fulfill_order(order_1.order_id)

    print("Stats after fulfilling order 1:")
    print_stats(app.stats_service.print_stats())

    app.order_service.fulfill_order(order_2.order_id)
    app.restaurant_service.change_menu(
        "Eat Fit",
        {"Idly": 60, "Vada": 40},
        2,
    )

    order_4 = app.order_service.place_order(["Idly"])
    print(format_order(order_4))

    print("Quick tests:")
    run_quick_tests()


if __name__ == "__main__":
    main()
