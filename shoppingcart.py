import uuid
from enum import Enum
from threading import Lock

class Product:

    def __init__(
        self,
        product_id,
        name,
        price,
        quantity
    ):
        self.id = product_id
        self.name = name
        self.price = price
        self.quantity = quantity

        self.lock = Lock()

    def reserve(self, qty):

        if qty > self.quantity:
            raise ValueError(
                f"Insufficient inventory for {self.name}"
            )

        self.quantity -= qty

    def release(self, qty):
        self.quantity += qty


class CartItem:

    def __init__(
        self,
        product_id,
        quantity
    ):
        self.product_id = product_id
        self.quantity = quantity


class Cart:

    def __init__(self, user_id):

        self.user_id = user_id

        # product_id -> CartItem
        self.items = {}

    def add_item(
        self,
        product_id,
        quantity
    ):

        if product_id in self.items:

            self.items[product_id].quantity += quantity

        else:

            self.items[product_id] = CartItem(
                product_id,
                quantity
            )

    def get_items(self):
        return list(self.items.values())


class OrderStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Order:

    def __init__(
        self,
        user_id,
        items,
        total
    ):

        self.id = str(uuid.uuid4())

        self.user_id = user_id

        self.items = items

        self.total = total

        self.status = OrderStatus.PENDING

class InventoryService:

    def __init__(self, product_repo):
        self.product_repo = product_repo

    def reserve(self, cart_items):

        locked_products = []

        # -------------------------------------------------
        # deterministic locking order
        # avoids deadlock
        # -------------------------------------------------
        sorted_items = sorted(
            cart_items,
            key=lambda item: item.product_id
        )

        # -------------------------------------------------
        # acquire locks
        # -------------------------------------------------
        for item in sorted_items:

            product = self.product_repo[item.product_id]

            product.lock.acquire()

            locked_products.append(product)

        try:

            # -------------------------------------------------
            # validate inventory
            # -------------------------------------------------
            for item in sorted_items:

                product = self.product_repo[item.product_id]

                if product.quantity < item.quantity:

                    raise ValueError(
                        f"Insufficient inventory for "
                        f"{product.name}"
                    )

            # -------------------------------------------------
            # reserve inventory
            # -------------------------------------------------
            for item in sorted_items:

                product = self.product_repo[item.product_id]

                product.reserve(item.quantity)

            return locked_products

        except Exception:

            for product in locked_products:
                product.lock.release()

            raise

    def release(self, order_items):

        for item in order_items:

            product = self.product_repo[item.product_id]

            product.release(item.quantity)


# =========================================================
# PAYMENT STRATEGY
# =========================================================

class PaymentStrategy:

    def pay(self, amount):
        raise NotImplementedError

    def refund(self, amount):
        raise NotImplementedError


class UpiPayment(PaymentStrategy):

    def pay(self, amount):

        print(f"Paid ₹{amount} via UPI")

        return True

    def refund(self, amount):

        print(f"Refunded ₹{amount} via UPI")

        return True


class OrderService:

    def __init__(
        self,
        product_repo,
        payment_strategy
    ):

        self.product_repo = product_repo

        self.inventory_service = InventoryService(
            product_repo
        )

        self.payment_strategy = payment_strategy

        self.orders = {}


    def place_order(self, cart):

        cart_items = cart.get_items()

        # -------------------------------------------------
        # reserve inventory
        # -------------------------------------------------
        locked_products = self.inventory_service.reserve(
            cart_items
        )

        try:

            # -------------------------------------------------
            # calculate total
            # -------------------------------------------------
            total = 0

            for item in cart_items:

                product = self.product_repo[
                    item.product_id
                ]

                total += (
                    product.price *
                    item.quantity
                )

            # -------------------------------------------------
            # create order
            # -------------------------------------------------
            order = Order(
                user_id=cart.user_id,
                items=cart_items,
                total=total
            )

            self.orders[order.id] = order

            print(
                f"Order placed -> {order.id}"
            )

            return order

        finally:

            for product in locked_products:
                product.lock.release()

    # =====================================================
    # CONFIRM ORDER
    # =====================================================
    def confirm_order(self, order_id):

        order = self.orders.get(order_id)

        if not order:
            raise ValueError("Order not found")

        if order.status != OrderStatus.PENDING:
            return order

        # -------------------------------------------------
        # payment step
        # -------------------------------------------------
        payment_success = self.payment_strategy.pay(
            order.total
        )

        if not payment_success:

            self.inventory_service.release(
                order.items
            )

            order.status = OrderStatus.CANCELLED

            return order

        order.status = OrderStatus.CONFIRMED

        print(
            f"Order confirmed -> {order.id}"
        )

        return order

    # =====================================================
    # CANCEL ORDER
    # =====================================================
    def cancel_order(self, order_id):

        order = self.orders.get(order_id)

        if not order:
            raise ValueError("Order not found")

        if order.status == OrderStatus.CANCELLED:
            return order

        # -------------------------------------------------
        # release inventory
        # -------------------------------------------------
        self.inventory_service.release(
            order.items
        )

        # -------------------------------------------------
        # refund if already confirmed
        # -------------------------------------------------
        if order.status == OrderStatus.CONFIRMED:

            self.payment_strategy.refund(
                order.total
            )

        order.status = OrderStatus.CANCELLED

        print(
            f"Order cancelled -> {order.id}"
        )

        return order


def main():


    products = {
        "p1": Product(
            "p1",
            "Phone",
            100,
            5
        ),

        "p2": Product(
            "p2",
            "Laptop",
            500,
            3
        )
    }


    cart = Cart("user1")

    cart.add_item("p1", 2)

    cart.add_item("p2", 1)

    service = OrderService(
        products,
        UpiPayment()
    )

    order = service.place_order(cart)

    print(
        f"Order Status -> "
        f"{order.status.value}"
    )

    order = service.confirm_order(order.id)

    print(
        f"Order Status -> "
        f"{order.status.value}"
    )

    # =====================================================
    # CANCEL ORDER
    # =====================================================
    order = service.cancel_order(order.id)

    print(
        f"Order Status -> "
        f"{order.status.value}"
    )


if __name__ == "__main__":
    main()