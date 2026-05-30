from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional, Tuple
import uuid


class OrderStatus(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FULFILLED = "FULFILLED"


class FoodOrderingError(Exception):
    pass


class ValidationError(FoodOrderingError):
    pass


class EntityNotFoundError(FoodOrderingError):
    pass


class OrderRejectedError(FoodOrderingError):
    pass


@dataclass(frozen=True)
class AddRestaurantRequest:
    name: str
    menu: Dict[str, int]
    capacity: int


@dataclass(frozen=True)
class ChangeMenuRequest:
    restaurant_name: str
    menu: Dict[str, int]
    capacity: Optional[int] = None


@dataclass(frozen=True)
class PlaceOrderRequest:
    items: List[str]


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
        self.in_flight_items = max(0, self.in_flight_items - count)


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
        self._lock = RLock()

    def save(self, restaurant: Restaurant) -> None:
        with self._lock:
            key = self._key(restaurant.name)
            if key in self.restaurants:
                raise ValidationError(f"Restaurant already exists: {restaurant.name}")
            self.restaurants[key] = restaurant

    def get(self, restaurant_name: str) -> Restaurant:
        with self._lock:
            restaurant = self.restaurants.get(self._key(restaurant_name))
            if not restaurant:
                raise EntityNotFoundError(f"Restaurant not found: {restaurant_name}")
            return restaurant

    def list_all(self) -> List[Restaurant]:
        with self._lock:
            return list(self.restaurants.values())

    def replace_menu(
        self,
        restaurant_name: str,
        menu: Dict[str, int],
        capacity: Optional[int],
    ) -> None:
        restaurant = self.get(restaurant_name)

        with restaurant.lock:
            if capacity is not None:
                if capacity <= 0:
                    raise ValidationError("Capacity must be positive")
                if restaurant.in_flight_items > capacity:
                    raise ValidationError("New capacity is lower than in-flight item count")
                restaurant.max_capacity = capacity

            restaurant.menu = self._normalize_menu(menu)

    def _key(self, restaurant_name: str) -> str:
        return restaurant_name.strip().lower()

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
                raise EntityNotFoundError(f"Order not found: {order_id}")
            return order


class RestaurantSelectionStrategy(ABC):
    @abstractmethod
    def select(
        self,
        items: List[str],
        restaurants: List[Restaurant],
    ) -> Optional[List[OrderAssignment]]:
        pass


class LowestPriceSelectionStrategy(RestaurantSelectionStrategy):
    def select(
        self,
        items: List[str],
        restaurants: List[Restaurant],
    ) -> Optional[List[OrderAssignment]]:
        normalized_items = [item.strip().lower() for item in items]
        remaining_capacity = {
            restaurant.name: restaurant.remaining_capacity()
            for restaurant in restaurants
        }

        candidates_by_item = {
            item: self._candidates(item, restaurants)
            for item in normalized_items
        }

        if any(not candidates for candidates in candidates_by_item.values()):
            return None

        ordered_items = sorted(
            normalized_items,
            key=lambda item: (
                len(candidates_by_item[item]),
                min(price for _, price in candidates_by_item[item]),
                item,
            ),
        )

        assignments: List[OrderAssignment] = []

        if self._backtrack(
            ordered_items,
            0,
            remaining_capacity,
            candidates_by_item,
            assignments,
        ):
            return assignments

        return None

    def _candidates(
        self,
        item: str,
        restaurants: List[Restaurant],
    ) -> List[Tuple[Restaurant, int]]:
        candidates = []

        for restaurant in restaurants:
            price = restaurant.menu.get(item)
            if price is not None and restaurant.remaining_capacity() > 0:
                candidates.append((restaurant, price))

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate[1],
                candidate[0].name,
            ),
        )

    def _backtrack(
        self,
        ordered_items: List[str],
        index: int,
        remaining_capacity: Dict[str, int],
        candidates_by_item: Dict[str, List[Tuple[Restaurant, int]]],
        assignments: List[OrderAssignment],
    ) -> bool:
        if index == len(ordered_items):
            return True

        item = ordered_items[index]

        for restaurant, price in candidates_by_item[item]:
            if remaining_capacity[restaurant.name] <= 0:
                continue

            remaining_capacity[restaurant.name] -= 1
            assignments.append(OrderAssignment(item, restaurant.name, price))

            if self._backtrack(
                ordered_items,
                index + 1,
                remaining_capacity,
                candidates_by_item,
                assignments,
            ):
                return True

            assignments.pop()
            remaining_capacity[restaurant.name] += 1

        return False


class RestaurantService:
    def __init__(self, restaurant_repo: RestaurantRepository):
        self.restaurant_repo = restaurant_repo

    def add_restaurant(self, request: AddRestaurantRequest) -> None:
        if not request.name.strip():
            raise ValidationError("Restaurant name cannot be empty")
        if request.capacity <= 0:
            raise ValidationError("Capacity must be positive")

        normalized_menu = self.restaurant_repo._normalize_menu(request.menu)
        restaurant = Restaurant(
            name=request.name.strip(),
            menu=normalized_menu,
            max_capacity=request.capacity,
        )
        self.restaurant_repo.save(restaurant)

    def change_menu(self, request: ChangeMenuRequest) -> None:
        self.restaurant_repo.replace_menu(
            request.restaurant_name,
            request.menu,
            request.capacity,
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

    def place_order(self, request: PlaceOrderRequest) -> Order:
        self._validate_items(request.items)

        restaurants = self.restaurant_repo.list_all()
        assignments = self.selection_strategy.select(request.items, restaurants)

        if not assignments:
            raise OrderRejectedError("Order cannot be fulfilled")

        restaurants_by_name = {
            restaurant.name: restaurant
            for restaurant in restaurants
        }
        selected_restaurants = [
            restaurants_by_name[name]
            for name in sorted({assignment.restaurant_name for assignment in assignments})
        ]

        for restaurant in selected_restaurants:
            restaurant.lock.acquire()

        try:
            if not self._can_still_fulfill(assignments, restaurants_by_name):
                raise OrderRejectedError("Order cannot be fulfilled")

            grouped_items = self._group_items_by_restaurant(assignments)

            for restaurant_name, items in grouped_items.items():
                restaurants_by_name[restaurant_name].reserve_items(items)

            order = Order(
                order_id=f"Order Id#{uuid.uuid4().hex[:6].upper()}",
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

        restaurants_by_name = {
            restaurant.name: restaurant
            for restaurant in self.restaurant_repo.list_all()
        }
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

    def _can_still_fulfill(
        self,
        assignments: List[OrderAssignment],
        restaurants_by_name: Dict[str, Restaurant],
    ) -> bool:
        grouped_items = self._group_items_by_restaurant(assignments)

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

        for restaurant in self.restaurant_repo.list_all():
            with restaurant.lock:
                stats[restaurant.name] = restaurant.remaining_capacity()

        return stats

    def served_items(self) -> Dict[str, Dict[str, int]]:
        stats = {}

        for restaurant in self.restaurant_repo.list_all():
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
        AddRestaurantRequest(
            "A2B",
            {
                "Idly": 40,
                "Vada": 30,
                "Paper Plain Dosa": 50,
            },
            4,
        )
    )
    app.restaurant_service.add_restaurant(
        AddRestaurantRequest(
            "Rasaganga",
            {
                "Idly": 45,
                "Set Dosa": 60,
                "Poori": 25,
            },
            6,
        )
    )
    app.restaurant_service.add_restaurant(
        AddRestaurantRequest(
            "Eat Fit",
            {
                "Idly": 30,
                "Vada": 40,
            },
            2,
        )
    )


def print_stats(stats: Dict[str, int]) -> None:
    for restaurant_name, capacity in stats.items():
        print(f"{restaurant_name}: {capacity}")


def main() -> None:
    app = FoodOrderingApp()
    seed_data(app)

    order_1 = app.order_service.place_order(PlaceOrderRequest(["Idly", "Poori"]))
    print(format_order(order_1))

    order_2 = app.order_service.place_order(PlaceOrderRequest(["Idly", "Vada"]))
    print(format_order(order_2))

    print("Stats after two orders:")
    print_stats(app.stats_service.print_stats())

    order_3 = app.order_service.place_order(PlaceOrderRequest(["Idly"]))
    print(format_order(order_3))

    app.order_service.fulfill_order(order_1.order_id)

    print("Stats after fulfilling order 1:")
    print_stats(app.stats_service.print_stats())

    app.order_service.fulfill_order(order_2.order_id)
    app.restaurant_service.change_menu(
        ChangeMenuRequest(
            "Eat Fit",
            {
                "Idly": 60,
                "Vada": 40,
            },
            2,
        )
    )

    order_4 = app.order_service.place_order(PlaceOrderRequest(["Idly"]))
    print(format_order(order_4))


if __name__ == "__main__":
    main()
