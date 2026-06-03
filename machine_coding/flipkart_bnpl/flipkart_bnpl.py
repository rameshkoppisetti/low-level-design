from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional


BNPL_DAYS = 30
BLACKLIST_DEFAULT_COUNT = 3


class DueStatus(Enum):
    PENDING = "PENDING"
    DELAYED = "DELAYED"


@dataclass
class Product:
    name: str
    count: int
    price: int
    lock: RLock = field(default_factory=RLock, repr=False)


@dataclass
class User:
    user_id: str
    credit_limit: int
    lock: RLock = field(default_factory=RLock, repr=False)


@dataclass
class Order:
    order_id: str
    user_id: str
    items: Dict[str, int]
    purchase_day: int
    total_amount: int
    pending_amount: int

    def due_day(self) -> int:
        return self.purchase_day + BNPL_DAYS


class InventoryRepository:
    def __init__(self):
        self.products: Dict[str, Product] = {}
        self._lock = RLock()

    def upsert(self, name: str, count: int, price: int) -> None:
        key = self._key(name)
        with self._lock:
            product = self.products.get(key)
            if product:
                with product.lock:
                    product.count += count
                    product.price = price
            else:
                self.products[key] = Product(name.strip(), count, price)

    def get(self, name: str) -> Optional[Product]:
        with self._lock:
            return self.products.get(self._key(name))

    def list_all(self) -> List[Product]:
        with self._lock:
            return list(self.products.values())

    def _key(self, name: str) -> str:
        return name.strip()


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def create_if_absent(self, user_id: str, credit_limit: int) -> None:
        with self._lock:
            if user_id not in self.users:
                self.users[user_id] = User(user_id, credit_limit)

    def get(self, user_id: str) -> Optional[User]:
        with self._lock:
            return self.users.get(user_id)


class OrderRepository:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.orders_by_user: Dict[str, List[str]] = {}
        self._lock = RLock()

    def exists(self, order_id: str) -> bool:
        with self._lock:
            return order_id in self.orders

    def save(self, order: Order) -> None:
        with self._lock:
            self.orders[order.order_id] = order
            self.orders_by_user.setdefault(order.user_id, []).append(order.order_id)

    def get(self, order_id: str) -> Optional[Order]:
        with self._lock:
            return self.orders.get(order_id)

    def list_by_user(self, user_id: str) -> List[Order]:
        with self._lock:
            return [
                self.orders[order_id]
                for order_id in self.orders_by_user.get(user_id, [])
            ]


class BNPLService:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        user_repo: UserRepository,
        order_repo: OrderRepository,
    ):
        self.inventory_repo = inventory_repo
        self.user_repo = user_repo
        self.order_repo = order_repo
        self._lock = RLock()

    def seed_inventory(self, inventory_lines: List[str]) -> None:
        for line in inventory_lines:
            name, count_text, price_text = line.split(",")
            name = name.strip()
            count = int(count_text)
            price = int(price_text)
            if not name or count < 0 or price <= 0:
                continue
            self.inventory_repo.upsert(name, count, price)

    def view_inventory(self) -> List[str]:
        rows = []
        for product in self.inventory_repo.list_all():
            with product.lock:
                rows.append(f"{product.name},{product.count},{product.price}")
        return sorted(rows, key=lambda row: row.split(",", 1)[0])

    def register_user(self, user_id: str, credit_limit: int) -> None:
        if not user_id.strip() or credit_limit < 0:
            return
        self.user_repo.create_if_absent(user_id, credit_limit)

    def buy(
        self,
        order_id: str,
        user_id: str,
        items_with_quantity: List[str],
        purchase_day: int,
    ) -> bool:
        if not order_id.strip() or purchase_day < 0:
            return False

        with self._lock:
            user = self.user_repo.get(user_id)
            if not user or self.order_repo.exists(order_id):
                return False
            if self.is_blacklisted(user_id, purchase_day):
                return False

            requested_items = self._parse_items(items_with_quantity)
            if not requested_items:
                return False

            products = {}
            total = 0
            for item_name, quantity in requested_items.items():
                product = self.inventory_repo.get(item_name)
                if not product:
                    return False
                products[item_name] = product
                if quantity <= 0 or product.count < quantity:
                    return False
                total += product.price * quantity

            if total > self._available_credit(user_id):
                return False

            for item_name, quantity in requested_items.items():
                products[item_name].count -= quantity

            self.order_repo.save(
                Order(
                    order_id=order_id,
                    user_id=user_id,
                    items=dict(sorted(requested_items.items())),
                    purchase_day=purchase_day,
                    total_amount=total,
                    pending_amount=total,
                )
            )
            return True

    def clear_dues(
        self,
        user_id: str,
        order_ids_to_clear: List[str],
        clearing_day: int,
    ) -> None:
        if clearing_day < 0 or not self.user_repo.get(user_id):
            return

        with self._lock:
            for order_id in order_ids_to_clear:
                order = self.order_repo.get(order_id)
                if not order or order.user_id != user_id:
                    continue
                order.pending_amount = 0

    def account_summary(self, user_id: str, as_of_day: int) -> List[str]:
        user = self.user_repo.get(user_id)
        if not user or as_of_day < 0:
            return []

        rows = [f"CREDIT_AVAILABLE,{self._available_credit(user_id)}"]
        orders = sorted(
            self.order_repo.list_by_user(user_id),
            key=lambda order: (-order.purchase_day, order.order_id),
        )

        for order in orders:
            item_text = self._format_items(order.items)
            rows.append(
                f"ORDER,{order.order_id},{order.purchase_day},"
                f"{order.total_amount},{item_text}"
            )

            if order.pending_amount > 0 and order.purchase_day <= as_of_day:
                rows.append(
                    f"DUE,{order.order_id},{order.purchase_day},{order.due_day()},"
                    f"{order.pending_amount},{self._due_status(order, as_of_day).value},"
                    f"{item_text}"
                )

        return rows

    def is_blacklisted(self, user_id: str, as_of_day: int) -> bool:
        if not self.user_repo.get(user_id) or as_of_day < 0:
            return False

        delayed_count = 0
        for order in self.order_repo.list_by_user(user_id):
            if order.pending_amount > 0 and self._due_status(order, as_of_day) == DueStatus.DELAYED:
                delayed_count += 1
                if delayed_count >= BLACKLIST_DEFAULT_COUNT:
                    return True
        return delayed_count >= BLACKLIST_DEFAULT_COUNT

    def _available_credit(self, user_id: str) -> int:
        user = self.user_repo.get(user_id)
        if not user:
            return 0

        pending = sum(
            order.pending_amount
            for order in self.order_repo.list_by_user(user_id)
        )
        return user.credit_limit - pending

    def _parse_items(self, items_with_quantity: List[str]) -> Dict[str, int]:
        items: Dict[str, int] = {}
        for encoded_item in items_with_quantity:
            try:
                name, quantity_text = encoded_item.split(",")
                name = name.strip()
                quantity = int(quantity_text)
            except ValueError:
                return {}
            if not name or quantity <= 0:
                return {}
            items[name] = items.get(name, 0) + quantity
        return items

    def _format_items(self, items: Dict[str, int]) -> str:
        return "|".join(f"{name}:{quantity}" for name, quantity in sorted(items.items()))

    def _due_status(self, order: Order, as_of_day: int) -> DueStatus:
        if as_of_day <= order.due_day():
            return DueStatus.PENDING
        return DueStatus.DELAYED


class FlipkartBNPL:
    def __init__(self):
        self.inventory_repo = InventoryRepository()
        self.user_repo = UserRepository()
        self.order_repo = OrderRepository()
        self.bnpl_service = BNPLService(
            self.inventory_repo,
            self.user_repo,
            self.order_repo,
        )

    def seedInventory(self, inventoryLines: List[str]) -> None:
        self.bnpl_service.seed_inventory(inventoryLines)

    def viewInventory(self) -> List[str]:
        return self.bnpl_service.view_inventory()

    def registerUser(self, user: str, creditLimit: int) -> None:
        self.bnpl_service.register_user(user, creditLimit)

    def buy(
        self,
        orderId: str,
        user: str,
        itemsWithQuantity: List[str],
        purchaseDay: int,
    ) -> bool:
        return self.bnpl_service.buy(orderId, user, itemsWithQuantity, purchaseDay)

    def clearDues(
        self,
        user: str,
        orderIdsToClear: List[str],
        clearingDay: int,
    ) -> None:
        self.bnpl_service.clear_dues(user, orderIdsToClear, clearingDay)

    def accountSummary(self, user: str, asOfDay: int) -> List[str]:
        return self.bnpl_service.account_summary(user, asOfDay)

    def isBlacklisted(self, user: str, asOfDay: int) -> bool:
        return self.bnpl_service.is_blacklisted(user, asOfDay)


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_basic_buy_summary() -> None:
    bnpl = FlipkartBNPL()
    bnpl.seedInventory(["Shoes,5,200", "Watch,10,1000", "T-Shirt,14,2000"])
    bnpl.registerUser("Akshay", 5000)

    assert_equal(
        True,
        bnpl.buy("OD_1", "Akshay", ["Shoes,2", "Watch,1"], 19000),
        "buy succeeds",
    )
    assert_equal(
        ["Shoes,3,200", "T-Shirt,14,2000", "Watch,9,1000"],
        bnpl.viewInventory(),
        "inventory view",
    )
    assert_equal(
        [
            "CREDIT_AVAILABLE,3600",
            "ORDER,OD_1,19000,1400,Shoes:2|Watch:1",
            "DUE,OD_1,19000,19030,1400,PENDING,Shoes:2|Watch:1",
        ],
        bnpl.accountSummary("Akshay", 19010),
        "account summary",
    )


def test_buy_rejected_atomically() -> None:
    bnpl = FlipkartBNPL()
    bnpl.seedInventory(["Phone,1,6000"])
    bnpl.registerUser("Riya", 5000)

    assert_equal(False, bnpl.buy("OD_1", "Riya", ["Phone,1"], 19005), "credit reject")
    assert_equal(["Phone,1,6000"], bnpl.viewInventory(), "inventory unchanged")
    assert_equal(["CREDIT_AVAILABLE,5000"], bnpl.accountSummary("Riya", 19005), "summary empty")


def test_blacklist_and_clear_dues() -> None:
    bnpl = FlipkartBNPL()
    bnpl.seedInventory(["Book,10,100"])
    bnpl.registerUser("Neha", 1000)

    bnpl.buy("OD_1", "Neha", ["Book,1"], 100)
    bnpl.buy("OD_2", "Neha", ["Book,1"], 101)
    bnpl.buy("OD_3", "Neha", ["Book,1"], 102)

    assert_equal(True, bnpl.isBlacklisted("Neha", 140), "blacklisted after 3 delayed dues")
    assert_equal(False, bnpl.buy("OD_4", "Neha", ["Book,1"], 140), "blacklisted buy rejected")
    bnpl.clearDues("Neha", ["OD_1", "OD_2", "OD_3"], 140)
    assert_equal(False, bnpl.isBlacklisted("Neha", 140), "blacklist removed after clearing")
    assert_equal(
        [
            "CREDIT_AVAILABLE,1000",
            "ORDER,OD_3,102,100,Book:1",
            "ORDER,OD_2,101,100,Book:1",
            "ORDER,OD_1,100,100,Book:1",
        ],
        bnpl.accountSummary("Neha", 140),
        "cleared summary",
    )


def test_duplicate_items_and_duplicate_inventory() -> None:
    bnpl = FlipkartBNPL()
    bnpl.seedInventory(["Book,2,100", "Book,3,120"])
    bnpl.registerUser("User1", 1000)

    assert_equal(["Book,5,120"], bnpl.viewInventory(), "inventory merges count and overwrites price")
    assert_equal(True, bnpl.buy("OD_1", "User1", ["Book,1", "Book,2"], 1), "duplicate order items merge")
    assert_equal(["Book,2,120"], bnpl.viewInventory(), "merged quantity reduced")


def run_tests() -> None:
    test_basic_buy_summary()
    test_buy_rejected_atomically()
    test_blacklist_and_clear_dues()
    test_duplicate_items_and_duplicate_inventory()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
