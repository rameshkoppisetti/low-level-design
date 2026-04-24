from enum import Enum
import uuid


# =========================
# DOMAIN MODELS
# =========================

class Product:
    """
    Represents a product within a store (tenant-specific).
    Handles inventory + pricing.
    """
    def __init__(self, id, name, price, quantity=0, description=None):
        self.id = id
        self.name = name
        self.price = price
        self.quantity = quantity
        self.description = description

    def remove_inventory(self, qty):
        """Deduct inventory safely."""
        if qty > self.quantity:
            raise ValueError(f"Insufficient inventory for {self.id}")
        self.quantity -= qty

    def add_inventory(self, qty):
        """Add inventory (used during restock or rollback)."""
        self.quantity += qty

    def __str__(self):
        return f"{self.id} {self.name} price={self.price} qty={self.quantity}"


class Store:
    """
    Represents a tenant.
    Each store has isolated product catalog.
    """
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self.products = {}  # product_id -> Product

    def add_product(self, product: Product):
        self.products[product.id] = product

    def get_product(self, product_id):
        return self.products.get(product_id)

    def __str__(self):
        return f"Store({self.tenant_id})"


class OrderItem:
    """
    Represents a product inside cart/order.
    """
    def __init__(self, product_id, quantity):
        self.product_id = product_id
        self.quantity = quantity

    def __str__(self):
        return f"{self.product_id} x {self.quantity}"


class Cart:
    """
    Represents user cart.
    Scoped to one tenant.
    """
    def __init__(self, tenant_id, user_id):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.items = {}  # product_id -> OrderItem

    def add_item(self, product_id, qty):
        if product_id in self.items:
            self.items[product_id].quantity += qty
        else:
            self.items[product_id] = OrderItem(product_id, qty)

    def remove_item(self, product_id, qty):
        if product_id not in self.items:
            raise ValueError("Item not in cart")

        item = self.items[product_id]
        if qty > item.quantity:
            raise ValueError("Removing more than present")

        item.quantity -= qty
        if item.quantity == 0:
            del self.items[product_id]

    def clear(self):
        self.items.clear()

    def __str__(self):
        return ", ".join(str(i) for i in self.items.values())


class User:
    def __init__(self, id, name, tenant_id):
        self.id = id
        self.name = name
        self.tenant_id = tenant_id


# =========================
# ORDER + STATUS
# =========================

class OrderStatus(Enum):
    PENDING = 1
    CONFIRMED = 2
    CANCELLED = 3


class Order:
    """
    Immutable order snapshot (no shared references).
    """
    def __init__(self, user_id, tenant_id, items, total_price):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.items = items  # deep copy of OrderItems
        self.total_price = total_price
        self.status = OrderStatus.PENDING

    def __str__(self):
        return f"Order({self.user_id}, total={self.total_price}, status={self.status})"


# =========================
# PAYMENT
# =========================

class PaymentStatus(Enum):
    PENDING = 1
    SUCCESS = 2
    FAILED = 3


class Payment:
    def __init__(self, order_id, user_id, amount):
        self.order_id = order_id
        self.user_id = user_id
        self.amount = amount
        self.status = PaymentStatus.PENDING


class PaymentService:
    """
    Pluggable interface for payment providers.
    """
    def pay(self, order: Order) -> Payment:
        raise NotImplementedError


class DummyPaymentService(PaymentService):
    """
    Mock payment service (always succeeds).
    """
    def pay(self, order: Order):
        print(f"[Payment] Processing {order.total_price}")
        payment = Payment(order.id, order.user_id, order.total_price)
        payment.status = PaymentStatus.SUCCESS
        return payment


# =========================
# ORDER SERVICE
# =========================

class OrderService:
    """
    Handles order placement, validation, lifecycle.
    """

    def __init__(self, payment_service: PaymentService):
        self.payment_service = payment_service
        self.orders = {}          # user_id -> {order_id -> Order}
        self.tenant_stores = {}   # tenant_id -> Store

    def register_store(self, store: Store):
        self.tenant_stores[store.tenant_id] = store

    def place_order(self, store: Store, cart: Cart):
        # Step 1: Validate tenant
        if store.tenant_id != cart.tenant_id:
            raise ValueError("Tenant mismatch between cart and store")

        # Step 2: Validate inventory
        inventory = self._validate_inventory(store, cart)

        # Step 3: Deduct inventory + compute total
        total = self._deduct_inventory(inventory)

        # Step 4: Create order snapshot
        order = self._create_order(store, cart, total)

        # Step 5: Payment
        payment = self.payment_service.pay(order)

        # Step 6: Confirm or rollback
        self._finalize_order(payment, order, store)

        # Step 7: Clear cart
        cart.clear()

        return order
    
    def _validate_inventory(self, store: Store, cart: Cart):
        inventory = []

        for item in cart.items.values():
            product = store.get_product(item.product_id)

            if not product:
                raise ValueError(f"Product {item.product_id} not found")

            if product.quantity < item.quantity:
                raise ValueError(f"Insufficient inventory for {item.product_id}")

            inventory.append((item, product))

        return inventory
    
    def _deduct_inventory(self, inventory):
        total = 0

        for item, product in inventory:
            product.remove_inventory(item.quantity)
            total += item.quantity * product.price

        return total
    
    def _create_order(self, store: Store, cart: Cart, total):
        items_copy = [
            OrderItem(i.product_id, i.quantity)
            for i in cart.items.values()
        ]

        return Order(cart.user_id, store.tenant_id, items_copy, total)
    
    def _finalize_order(self, payment, order, store):
        if payment.status == PaymentStatus.SUCCESS:
            order.status = OrderStatus.CONFIRMED
        else:
            self._rollback(store, order)
            order.status = OrderStatus.CANCELLED


    def _rollback(self, store: Store, order: Order):
        for item in order.items:
            product = store.get_product(item.product_id)

            if not product:
                raise ValueError("Rollback failed: product missing")

            product.add_inventory(item.quantity)

    def get_orders(self, user: User):
        return self.orders.get(user.id, {}).values()


# =========================
# DEMO
# =========================

def main():
    store = Store("tenant_1")
    product = Product("p1", "Jacket", 100, 10)
    store.add_product(product)

    user = User("u1", "Satya", "tenant_1")

    cart = Cart("tenant_1", user.id)
    cart.add_item("p1", 2)

    payment = DummyPaymentService()
    order_service = OrderService(payment)
    order_service.register_store(store)

    order = order_service.place_order(store, cart)

    print(order)
    print("Remaining inventory:", product.quantity)


if __name__ == "__main__":
    main()
    
    """🧠 Q1: Why did you use dict (map) for cart instead of list?
✅ Ideal answer:

“I used a map for O(1) lookup and updates. It also prevents duplicate entries for the same product, which simplifies quantity management.”

👉 Bonus:

“List would require O(n) search and duplicate handling.”

🧠 Q2: Why create OrderItem instead of storing (product_id, qty)?
✅ Answer:

“Encapsulation. It allows us to extend fields later like price snapshot, discounts, or metadata without changing structure.”

🧠 Q3: Why copy cart items into Order?
✅ Answer:

“To avoid shared mutable state. Cart can change after order placement, so order must be an immutable snapshot.”

🔥 This is a very strong signal answer

🧠 Q4: What happens if payment fails?
✅ Answer:

“We rollback inventory using the order snapshot and mark order as CANCELLED to maintain consistency.”

🧠 Q5: Why validate inventory before deducting?
✅ Answer:

“To ensure atomicity at application level. If we deduct partially and fail midway, system becomes inconsistent.”

🧠 Q6: How would you handle concurrency?
✅ Answer:

“Use fine-grained locking at product level or optimistic locking using versioning. In distributed systems, we can use DB transactions or Redis locks.”

👉 Keep it simple:

“lock per product” is enough
🧠 Q7: How would you scale this?
✅ Answer:

“Partition data by tenant_id. Each store can be isolated across services or shards. Orders and inventory can be handled via event-driven systems.”

🧠 Q8: What DB schema would you use?
✅ Answer:
Stores(tenant_id)
Products(product_id, tenant_id, quantity, price)
Orders(order_id, user_id, tenant_id)
OrderItems(order_id, product_id, qty)

👉 Mention:

“tenant_id used for partitioning”

🧠 Q9: Why separate services (OrderService, PaymentService)?
✅ Answer:

“Separation of concerns and extensibility. Payment logic can change independently without impacting order flow.”

🧠 Q10: What would you improve if given more time?
✅ Answer:

Pick 2–3:

“Add concurrency control, persistence layer, retries for payment, and introduce event-driven architecture for order lifecycle.”

🧠 Q11: What’s a potential bug in your system?
✅ Answer (strong):

“Concurrent orders could oversell inventory since there’s no locking.”

🔥 This shows awareness

🧠 Q12: How to make system more robust?
✅ Answer:
idempotency keys for orders
retry mechanisms
audit logs
🧠 How you should behave in this round
Don’t over-explain
2–3 lines per answer
Use keywords:
“atomicity”
“isolation”
“extensibility”
“scalability”
    """