import time
from threading import Lock, Thread
from typing import Dict, List, Optional


class InventoryObserver:
    def on_low_stock(self, product_id: str, available_qty: int) -> None:
        raise NotImplementedError


class RestockAlertSystem(InventoryObserver):
    def on_low_stock(self, product_id: str, available_qty: int) -> None:
        print(f"[Alert] Product {product_id} is running low! Remaining: {available_qty}")


class Product:
    def __init__(self, product_id: str, name: str, initial_qty: int, threshold: int):
        if initial_qty < 0:
            raise ValueError("initial_qty cannot be negative")
        if threshold < 0:
            raise ValueError("threshold cannot be negative")

        self.id = product_id
        self.name = name
        self.available_qty = initial_qty
        self.reserved_qty = 0
        self.threshold = threshold
        self.observers: List[InventoryObserver] = []
        self._lock = Lock()

    def add_observer(self, observer: InventoryObserver) -> None:
        self.observers.append(observer)

    def reserve(self, qty: int) -> bool:
        self._validate_qty(qty)

        with self._lock:
            if self.available_qty < qty:
                return False

            self.available_qty -= qty
            self.reserved_qty += qty
            self._check_threshold()
            return True

    def confirm(self, qty: int) -> None:
        self._validate_qty(qty)

        with self._lock:
            self.reserved_qty = max(0, self.reserved_qty - qty)

    def release(self, qty: int) -> None:
        self._validate_qty(qty)

        with self._lock:
            releasable = min(qty, self.reserved_qty)
            self.reserved_qty -= releasable
            self.available_qty += releasable

    def _check_threshold(self) -> None:
        if self.available_qty <= self.threshold:
            for observer in self.observers:
                observer.on_low_stock(self.id, self.available_qty)

    def _validate_qty(self, qty: int) -> None:
        if qty <= 0:
            raise ValueError("quantity must be positive")


class Reservation:
    def __init__(self, reservation_id: str, product_id: str, qty: int, ttl_ms: int):
        self.id = reservation_id
        self.product_id = product_id
        self.quantity = qty
        self.expiry_time = time.time() + (ttl_ms / 1000.0)

    def is_expired(self) -> bool:
        return time.time() > self.expiry_time


class InventoryService:
    def __init__(self, cleanup_interval_seconds: float = 0.1):
        self.products: Dict[str, Product] = {}
        self.reservations: Dict[str, Reservation] = {}
        self._lock = Lock()
        self.running = True
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.cleanup_thread = Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

    def add_product(self, product: Product) -> None:
        with self._lock:
            self.products[product.id] = product

    def reserve_stock(
        self,
        reservation_id: str,
        product_id: str,
        qty: int,
        ttl_ms: int,
    ) -> bool:
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be positive")

        with self._lock:
            if reservation_id in self.reservations:
                return False
            product = self.products.get(product_id)

        if not product or not product.reserve(qty):
            return False

        with self._lock:
            self.reservations[reservation_id] = Reservation(
                reservation_id,
                product_id,
                qty,
                ttl_ms,
            )

        return True

    def confirm_purchase(self, reservation_id: str) -> bool:
        reservation = self._pop_active_reservation(reservation_id)
        if not reservation:
            return False

        product = self._get_product(reservation.product_id)
        if not product:
            return False

        product.confirm(reservation.quantity)
        return True

    def release_reservation(self, reservation_id: str) -> bool:
        with self._lock:
            reservation = self.reservations.pop(reservation_id, None)

        if not reservation:
            return False

        product = self._get_product(reservation.product_id)
        if product:
            product.release(reservation.quantity)

        return True

    def shutdown(self) -> None:
        self.running = False
        self.cleanup_thread.join(timeout=1)

    def _pop_active_reservation(self, reservation_id: str) -> Optional[Reservation]:
        with self._lock:
            reservation = self.reservations.get(reservation_id)

            if not reservation:
                return None

            if reservation.is_expired():
                return None

            return self.reservations.pop(reservation_id)

    def _get_product(self, product_id: str) -> Optional[Product]:
        with self._lock:
            return self.products.get(product_id)

    def _cleanup_loop(self) -> None:
        while self.running:
            time.sleep(self.cleanup_interval_seconds)
            self._cleanup_expired_reservations()

    def _cleanup_expired_reservations(self) -> None:
        expired = []

        with self._lock:
            for reservation_id, reservation in list(self.reservations.items()):
                if reservation.is_expired():
                    expired.append(reservation)
                    del self.reservations[reservation_id]

        for reservation in expired:
            product = self._get_product(reservation.product_id)
            if product:
                product.release(reservation.quantity)
            print(f"[TTL Cleanup] Expired Reservation: {reservation.id}")


if __name__ == "__main__":
    print("=== Inventory Management Simulation ===")
    service = InventoryService()
    alert_system = RestockAlertSystem()

    laptop = Product("PROD-01", "MacBook Pro", 6, 2)
    laptop.add_observer(alert_system)
    service.add_product(laptop)

    reservation_1 = service.reserve_stock("RES-101", "PROD-01", 3, 200)
    print(f"Reservation RES-101: {'SUCCESS' if reservation_1 else 'FAILED'}")

    reservation_2 = service.reserve_stock("RES-102", "PROD-01", 2, 1000)
    print(f"Reservation RES-102: {'SUCCESS' if reservation_2 else 'FAILED'}")

    time.sleep(0.3)

    confirmed = service.confirm_purchase("RES-102")
    print(f"Confirm RES-102: {'SUCCESS' if confirmed else 'FAILED'}")

    service.shutdown()
