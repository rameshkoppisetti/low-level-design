from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Dict, List, Optional, Set, Tuple


ORDER_PLACED = "order placed"
PINCODE_UNSERVICEABLE = "pincode unserviceable"
PAYMENT_NOT_SUPPORTED = "payment mode not supported"
INSUFFICIENT_INVENTORY = "insufficient product inventory"
INVENTORY_ADDED = "inventory added"


@dataclass(frozen=True)
class Seller:
    seller_id: str
    serviceable_pincodes: Set[str]
    payment_modes: Set[str]


@dataclass(frozen=True)
class Order:
    order_id: str
    destination_pincode: str
    seller_id: str
    product_id: int
    product_count: int
    payment_mode: str


class Helper04:
    def log(self, message: str) -> None:
        print(message)


class SellerRepository:
    def __init__(self):
        self.sellers: Dict[str, Seller] = {}
        self._lock = RLock()

    def create(self, seller: Seller) -> None:
        with self._lock:
            self.sellers[seller.seller_id] = seller

    def get(self, seller_id: str) -> Optional[Seller]:
        with self._lock:
            return self.sellers.get(seller_id)


class InventoryRepository:
    def __init__(self):
        self.inventory: Dict[Tuple[int, str], int] = {}
        self._lock = RLock()

    def add(self, product_id: int, seller_id: str, delta: int) -> None:
        with self._lock:
            key = (product_id, seller_id)
            self.inventory[key] = self.inventory.get(key, 0) + delta

    def get(self, product_id: int, seller_id: str) -> int:
        with self._lock:
            return self.inventory.get((product_id, seller_id), 0)

    def reserve(self, product_id: int, seller_id: str, count: int) -> bool:
        key = (product_id, seller_id)
        with self._lock:
            current = self.inventory.get(key, 0)
            if current < count:
                return False
            self.inventory[key] = current - count
            return True


class OrderRepository:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self._lock = RLock()

    def create(self, order: Order) -> None:
        with self._lock:
            self.orders[order.order_id] = order


class OrderInventoryService:
    def __init__(
        self,
        seller_repo: SellerRepository,
        inventory_repo: InventoryRepository,
        order_repo: OrderRepository,
        products_count: int,
        helper: Optional[Helper04],
    ):
        self.seller_repo = seller_repo
        self.inventory_repo = inventory_repo
        self.order_repo = order_repo
        self.products_count = products_count
        self.helper = helper

    def create_seller(
        self,
        sellerId: str,
        serviceablePincodes: List[str],
        paymentModes: List[str],
    ) -> None:
        seller = Seller(
            seller_id=sellerId,
            serviceable_pincodes={str(pincode) for pincode in serviceablePincodes},
            payment_modes={payment_mode.strip().lower() for payment_mode in paymentModes},
        )
        self.seller_repo.create(seller)
        self._log(f"seller created: {sellerId}")

    def add_inventory(self, productId: int, sellerId: str, delta: int) -> str:
        self.inventory_repo.add(productId, sellerId, delta)
        self._log(f"inventory added product={productId} seller={sellerId} delta={delta}")
        return INVENTORY_ADDED

    def get_inventory(self, productId: int, sellerId: str) -> int:
        if productId < 0 or productId >= self.products_count:
            return 0
        if not self.seller_repo.get(sellerId):
            return 0
        return self.inventory_repo.get(productId, sellerId)

    def create_order(
        self,
        orderId: str,
        destinationPincode: str,
        sellerId: str,
        productId: int,
        productCount: int,
        paymentMode: str,
    ) -> str:
        seller = self.seller_repo.get(sellerId)
        if not seller:
            return INSUFFICIENT_INVENTORY

        destination_pincode = str(destinationPincode)
        payment_mode = paymentMode.strip().lower()

        if destination_pincode not in seller.serviceable_pincodes:
            return PINCODE_UNSERVICEABLE

        if payment_mode not in seller.payment_modes:
            return PAYMENT_NOT_SUPPORTED

        if not self.inventory_repo.reserve(productId, sellerId, productCount):
            return INSUFFICIENT_INVENTORY

        self.order_repo.create(
            Order(
                order_id=orderId,
                destination_pincode=destination_pincode,
                seller_id=sellerId,
                product_id=productId,
                product_count=productCount,
                payment_mode=payment_mode,
            )
        )
        self._log(f"order placed: {orderId}")
        return ORDER_PLACED

    def _log(self, message: str) -> None:
        if self.helper:
            self.helper.log(message)


class OrderInventorySystem:
    def __init__(self, helper:Helper04, products_count: int):
        self.helper: Optional[Helper04] = helper
        self.products_count = products_count
        self.seller_repo = SellerRepository()
        self.inventory_repo = InventoryRepository()
        self.order_repo = OrderRepository()
        self.service = OrderInventoryService(
            self.seller_repo,
            self.inventory_repo,
            self.order_repo,
            self.products_count,
            self.helper,
        )
        self._lock = RLock()

    def createSeller(
        self,
        sellerId: str,
        serviceablePincodes: List[str],
        paymentModes: List[str],
    ) -> None:
        self.service.create_seller(sellerId, serviceablePincodes, paymentModes)

    def addInventory(self, productId: int, sellerId: str, delta: int) -> str:
        return self.service.add_inventory(productId, sellerId, delta)

    def getInventory(self, productId: int, sellerId: str) -> int:
        return self.service.get_inventory(productId, sellerId)

    def createOrder(
        self,
        orderId: str,
        destinationPincode: str,
        sellerId: str,
        productId: int,
        productCount: int,
        paymentMode: str,
    ) -> str:
        return self.service.create_order(
            orderId,
            destinationPincode,
            sellerId,
            productId,
            productCount,
            paymentMode,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_sample_flow() -> None:
    system = OrderInventorySystem(Helper04(), 10)

    system.createSeller(
        "seller-0",
        ["110001", "560092", "452001", "700001"],
        ["netbanking", "cash", "upi"],
    )
    system.createSeller(
        "seller-1",
        ["400050", "110001", "600032", "560092"],
        ["netbanking", "cash", "upi"],
    )

    assert_equal(INVENTORY_ADDED, system.addInventory(0, "seller-1", 52), "inventory seller-1")
    assert_equal(INVENTORY_ADDED, system.addInventory(0, "seller-0", 32), "inventory seller-0")
    assert_equal(
        ORDER_PLACED,
        system.createOrder("order-1", "400050", "seller-1", 0, 5, "upi"),
        "order 1 placed",
    )
    assert_equal(47, system.getInventory(0, "seller-1"), "seller-1 inventory reduced")
    assert_equal(
        ORDER_PLACED,
        system.createOrder("order-2", "560092", "seller-0", 0, 1, "upi"),
        "order 2 placed",
    )
    assert_equal(31, system.getInventory(0, "seller-0"), "seller-0 inventory reduced")


def test_order_failures_do_not_reduce_inventory() -> None:
    system = OrderInventorySystem(Helper04(), 5)
    system.createSeller("seller-1", ["400050"], ["upi"])
    system.addInventory(0, "seller-1", 3)

    assert_equal(
        PINCODE_UNSERVICEABLE,
        system.createOrder("o1", "560092", "seller-1", 0, 1, "upi"),
        "pincode failure",
    )
    assert_equal(3, system.getInventory(0, "seller-1"), "inventory unchanged")

    assert_equal(
        PAYMENT_NOT_SUPPORTED,
        system.createOrder("o2", "400050", "seller-1", 0, 1, "cash"),
        "payment failure",
    )
    assert_equal(3, system.getInventory(0, "seller-1"), "inventory unchanged")

    assert_equal(
        INSUFFICIENT_INVENTORY,
        system.createOrder("o3", "400050", "seller-1", 0, 4, "upi"),
        "inventory failure",
    )
    assert_equal(3, system.getInventory(0, "seller-1"), "inventory unchanged")


def run_tests() -> None:
    test_sample_flow()
    test_order_failures_do_not_reduce_inventory()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
