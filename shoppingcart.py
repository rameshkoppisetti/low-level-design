import uuid
from threading import Lock
from enum import Enum


# =========================
# DOMAIN
# =========================

class Product:
    def __init__(self, id, name, price, quantity):
        self.id = id
        self.name = name
        self.price = price
        self.quantity = quantity
        self.lock = Lock()

    def reserve(self, qty):
        if qty > self.quantity:
            raise ValueError("Insufficient inventory")
        self.quantity -= qty

    def release(self, qty):
        self.quantity += qty


class Cart:
    def __init__(self, user_id):
        self.user_id = user_id
        self.items = {}

    def add_item(self, product_id, qty):
        self.items[product_id] = self.items.get(product_id, 0) + qty


class OrderStatus(Enum):
    PENDING = 1
    CONFIRMED = 2
    CANCELLED = 3


class Order:
    def __init__(self, user_id, items, total):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.items = items
        self.total = total
        self.status = OrderStatus.PENDING


# =========================
# INVENTORY SERVICE
# =========================

class InventoryService:
    def __init__(self, product_repo):
        self.product_repo = product_repo

    def reserve(self, cart_items):
        locked = []

        for pid in sorted(cart_items.keys()):
            p = self.product_repo[pid]
            p.lock.acquire()
            locked.append(p)

        try:
            for pid, qty in cart_items.items():
                if self.product_repo[pid].quantity < qty:
                    raise ValueError("Insufficient inventory")

            for pid, qty in cart_items.items():
                self.product_repo[pid].reserve(qty)

            return locked

        except:
            for p in locked:
                p.lock.release()
            raise

    def release(self, items):
        for pid, qty in items.items():
            self.product_repo[pid].release(qty)


# =========================
# PAYMENT STRATEGY
# =========================

class PaymentStrategy:
    def pay(self, amount):
        raise NotImplementedError


class UpiPayment(PaymentStrategy):
    def pay(self, amount):
        print(f"Paid ₹{amount} via UPI")
        return True


# =========================
# ORDER SERVICE
# =========================

class OrderService:
    def __init__(self, product_repo, payment_strategy):
        self.product_repo = product_repo
        self.inventory = InventoryService(product_repo)
        self.payment_strategy = payment_strategy
        self.orders = {}

    def place_order(self, cart):
        # reserve inventory
        locked = self.inventory.reserve(cart.items)

        try:
            total = sum(
                self.product_repo[pid].price * qty
                for pid, qty in cart.items.items()
            )

            order = Order(cart.user_id, dict(cart.items), total)

            self.orders[order.id] = order

            return order

        finally:
            for p in locked:
                p.lock.release()

    def confirm_order(self, order_id):
        order = self.orders.get(order_id)

        if not order:
            raise ValueError("Order not found")

        if order.status != OrderStatus.PENDING:
            return order

        # payment step
        if not self.payment_strategy.pay(order.total):
            self.inventory.release(order.items)
            order.status = OrderStatus.CANCELLED
            return order

        order.status = OrderStatus.CONFIRMED
        return order


# =========================
# DEMO
# =========================

def main():
    products = {
        "p1": Product("p1", "Phone", 100, 5),
        "p2": Product("p2", "Laptop", 500, 3),
    }

    cart = Cart("user1")
    cart.add_item("p1", 2)
    cart.add_item("p2", 1)

    service = OrderService(products, UpiPayment())

    # step 1: create order (PENDING)
    order = service.place_order(cart)
    print("Placed:", order.status)

    # step 2: confirm order (payment)
    order = service.confirm_order(order.id)
    print("Final:", order.status)


if __name__ == "__main__":
    main()