import threading
import uuid
from enum import Enum
from abc import ABC, abstractmethod


class Product:

    def __init__(
        self,
        name,
        description,
        price,
        quantity
    ):

        self.id = str(uuid.uuid4())

        self.name = name
        self.description = description
        self.price = price
        self.quantity = quantity

        self.lock = threading.Lock()

    def reserve(self, quantity):

        if quantity <= 0:
            raise ValueError("Invalid quantity")

        if quantity > self.quantity:
            raise ValueError(
                f"{self.name} out of stock"
            )

        self.quantity -= quantity

    def release(self, quantity):

        if quantity <= 0:
            raise ValueError("Invalid quantity")

        self.quantity += quantity

    def is_available(self, quantity):

        if quantity <= 0:
            return False

        return self.quantity >= quantity

    def __repr__(self):

        return (
            f"Product("
            f"name={self.name}, "
            f"price={self.price}, "
            f"quantity={self.quantity})"
        )


class InventoryService:

    def __init__(self):
        self.products = {}

    def add_product(self, product):
        self.products[product.id] = product

    def get_product(self, product_id):
        return self.products.get(product_id)

    def reserve_inventory(self, cart_items):

        locked_products = []

        sorted_items = sorted(
            cart_items,
            key=lambda item: item.product_id
        )

        try:

            for item in sorted_items:

                product = self.get_product(
                    item.product_id
                )

                if not product:
                    raise ValueError(
                        "Product not found"
                    )

                product.lock.acquire()

                locked_products.append(product)

            for item in sorted_items:

                product = self.get_product(
                    item.product_id
                )

                if not product.is_available(
                    item.quantity
                ):
                    raise ValueError(
                        f"{product.name} out of stock"
                    )

            for item in sorted_items:

                product = self.get_product(
                    item.product_id
                )

                product.reserve(item.quantity)

            return locked_products

        except Exception:

            for product in locked_products:
                product.lock.release()

            raise

    def release_inventory(self, order_items):

        for item in order_items:

            product = self.get_product(
                item.product_id
            )

            if product:
                product.release(item.quantity)


class User:

    def __init__(self, name):

        self.id = str(uuid.uuid4())

        self.name = name


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

        self.id = str(uuid.uuid4())

        self.user_id = user_id

        self.items = {}

    def add_to_cart(
        self,
        product_id,
        quantity
    ):

        if quantity <= 0:
            raise ValueError("Invalid quantity")

        if product_id not in self.items:

            self.items[product_id] = CartItem(
                product_id,
                quantity
            )

        else:

            self.items[
                product_id
            ].quantity += quantity

    def remove_from_cart(
        self,
        product_id,
        quantity
    ):

        if product_id not in self.items:
            raise ValueError(
                "Product not in cart"
            )

        cart_item = self.items[product_id]

        if quantity > cart_item.quantity:
            raise ValueError(
                "Invalid quantity"
            )

        cart_item.quantity -= quantity

        if cart_item.quantity == 0:
            del self.items[product_id]

    def get_items(self):
        return list(self.items.values())

    def clear(self):
        self.items.clear()


class OrderStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OrderItem:

    def __init__(
        self,
        product_id,
        quantity,
        price
    ):

        self.product_id = product_id
        self.quantity = quantity
        self.price = price


class Order:

    def __init__(
        self,
        user,
        items,
        total_price
    ):

        self.id = str(uuid.uuid4())

        self.user = user

        self.items = items

        self.total_price = total_price

        self.status = OrderStatus.PENDING

    def update_status(self, status):
        self.status = status


class SearchService:

    def __init__(self, inventory_service):

        self.inventory_service = inventory_service

        self.products_name_index = {}

        self.generate_indexes()

    def generate_indexes(self):

        self.products_name_index.clear()

        for product in (
            self.inventory_service.products.values()
        ):

            products = self.products_name_index.get(
                product.name.lower(),
                []
            )

            products.append(product)

            self.products_name_index[
                product.name.lower()
            ] = products

    def search_by_name(self, name):

        return self.products_name_index.get(
            name.lower(),
            []
        )


class PaymentStrategy(ABC):

    @abstractmethod
    def pay(self, order, amount):
        pass

    @abstractmethod
    def refund(self, order, amount):
        pass


class CreditCardStrategy(PaymentStrategy):

    def pay(self, order, amount):

        print(
            f"Payment success "
            f"for order={order.id} "
            f"amount={amount}"
        )

        return True

    def refund(self, order, amount):

        print(
            f"Refund success "
            f"for order={order.id} "
            f"amount={amount}"
        )

        return True


class OrderService:

    def __init__(
        self,
        inventory_service,
        payment_strategy
    ):

        self.inventory_service = (
            inventory_service
        )

        self.payment_strategy = (
            payment_strategy
        )

        self.orders = {}

    def place_order(
        self,
        user,
        cart
    ):

        cart_items = cart.get_items()

        locked_products = (
            self.inventory_service
            .reserve_inventory(cart_items)
        )

        try:

            total = 0

            order_items = []

            for item in cart_items:

                product = (
                    self.inventory_service
                    .get_product(item.product_id)
                )

                total += (
                    product.price *
                    item.quantity
                )

                order_items.append(
                    OrderItem(
                        product_id=product.id,
                        quantity=item.quantity,
                        price=product.price
                    )
                )

            order = Order(
                user=user,
                items=order_items,
                total_price=total
            )

            self.orders.setdefault(
                user.id,
                {}
            )[order.id] = order

            print(
                f"Order created -> {order.id}"
            )

            return order

        finally:

            for product in reversed(
                locked_products
            ):
                product.lock.release()

    def confirm_order(
        self,
        user_id,
        order_id
    ):

        order = self.orders.get(
            user_id,
            {}
        ).get(order_id)

        if not order:
            raise ValueError(
                "Order not found"
            )

        if order.status != OrderStatus.PENDING:
            return order

        payment_success = (
            self.payment_strategy.pay(
                order,
                order.total_price
            )
        )

        if payment_success:

            order.update_status(
                OrderStatus.CONFIRMED
            )

        else:

            self.inventory_service.release_inventory(
                order.items
            )

            order.update_status(
                OrderStatus.FAILED
            )

        return order

    def cancel_order(
        self,
        user_id,
        order_id
    ):

        order = self.orders.get(
            user_id,
            {}
        ).get(order_id)

        if not order:
            raise ValueError(
                "Order not found"
            )

        if order.status == OrderStatus.CANCELLED:
            return order

        self.inventory_service.release_inventory(
            order.items
        )

        if order.status == OrderStatus.CONFIRMED:

            self.payment_strategy.refund(
                order,
                order.total_price
            )

        order.update_status(
            OrderStatus.CANCELLED
        )

        return order


def main():

    inventory = InventoryService()

    phone = Product(
        "Phone",
        "Phone Description",
        100,
        5
    )

    laptop = Product(
        "Laptop",
        "Laptop Description",
        500,
        3
    )

    inventory.add_product(phone)
    inventory.add_product(laptop)

    search_service = SearchService(
        inventory
    )

    results = search_service.search_by_name(
        "Phone"
    )

    print(results)

    user = User("satya")

    cart = Cart(user.id)

    cart.add_to_cart(phone.id, 2)

    cart.add_to_cart(laptop.id, 1)

    order_service = OrderService(
        inventory,
        CreditCardStrategy()
    )

    order = order_service.place_order(
        user,
        cart
    )

    print(
        f"Placed Order Status -> "
        f"{order.status.value}"
    )

    order = order_service.confirm_order(
        user.id,
        order.id
    )

    print(
        f"Confirmed Order Status -> "
        f"{order.status.value}"
    )

    order = order_service.cancel_order(
        user.id,
        order.id
    )

    print(
        f"Cancelled Order Status -> "
        f"{order.status.value}"
    )

    print(phone)
    print(laptop)


if __name__ == "__main__":
    main()