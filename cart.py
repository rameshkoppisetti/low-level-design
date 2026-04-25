"""
✅ Step 1: Clarify Requirements (What Interviewer Wants)

We must support:

Base price of products

Product-level discounts

Cart-level discounts

Delivery charges

Taxes (optional but good to add)

Coupons (follow-up)

🏗 High-Level Design
Entities:

Product

CartItem

Cart

Discount (Strategy)

Coupon (Strategy)

DeliveryPolicy

PriceCalculator
"""
from abc import ABC, abstractmethod


# =========================
# PRODUCT
# =========================

class Product:
    def __init__(self, name, price):
        self.name = name
        self.price = price


# =========================
# DISCOUNT STRATEGY
# =========================

class Discount(ABC):
    @abstractmethod
    def apply(self, amount):
        pass


class FlatDiscount(Discount):
    def __init__(self, value):
        self.value = value

    def apply(self, amount):
        return min(self.value, amount)


class PercentageDiscount(Discount):
    def __init__(self, percent):
        self.percent = percent

    def apply(self, amount):
        return amount * self.percent / 100


# =========================
# CART ITEM
# =========================

class CartItem:
    def __init__(self, product, quantity=1, discount: Discount = None):
        self.product = product
        self.quantity = quantity
        self.discount = discount

    def get_total_price(self):
        base_total = self.product.price * self.quantity

        if self.discount:
            discount_value = self.discount.apply(base_total)
            return base_total - discount_value

        return base_total


# =========================
# COUPON (Cart-level discount)
# =========================

class Coupon(ABC):
    @abstractmethod
    def apply(self, amount):
        pass


class MinAmountPercentageCoupon(Coupon):
    def __init__(self, percent, min_amount):
        self.percent = percent
        self.min_amount = min_amount

    def apply(self, amount):
        if amount >= self.min_amount:
            return amount * self.percent / 100
        return 0

"""
Q: What if multiple coupons apply?

Options:

Allow only one coupon (simple system)

Use Chain of Responsibility

Use Composite Coupon (apply sequentially)
"""
class CompositeCoupon(Coupon):
    def __init__(self, coupons):
        self.coupons = coupons

    def apply(self, amount):
        total_discount = 0
        for coupon in self.coupons:
            discount = coupon.apply(amount - total_discount)
            total_discount += discount
        return total_discount

# =========================
# DELIVERY POLICY
# =========================

class DeliveryPolicy:
    def __init__(self, delivery_charge, free_above):
        self.delivery_charge = delivery_charge
        self.free_above = free_above

    def calculate(self, amount):
        if amount >= self.free_above:
            return 0
        return self.delivery_charge


# =========================
# CART
# =========================

class Cart:
    def __init__(self):
        self.items = []
        self.coupon = None

    def add_item(self, cart_item):
        self.items.append(cart_item)

    def apply_coupon(self, coupon):
        self.coupon = coupon


# =========================
# PRICE CALCULATOR
# =========================

class PriceCalculator:
    TAX_PERCENT = 10

    def __init__(self, delivery_policy):
        self.delivery_policy = delivery_policy

    def calculate(self, cart: Cart):

        # 1️⃣ Product level calculation
        subtotal = sum(item.get_total_price() for item in cart.items)

        # 2️⃣ Cart-level coupon
        coupon_discount = 0
        if cart.coupon:
            coupon_discount = cart.coupon.apply(subtotal)

        amount_after_coupon = subtotal - coupon_discount

        # 3️⃣ Tax
        tax = amount_after_coupon * self.TAX_PERCENT / 100

        # 4️⃣ Delivery
        delivery_fee = self.delivery_policy.calculate(amount_after_coupon)

        final_amount = amount_after_coupon + tax + delivery_fee

        return {
            "Subtotal": subtotal,
            "Coupon Discount": coupon_discount,
            "Tax": tax,
            "Delivery": delivery_fee,
            "Final Amount": final_amount
        }

# =========================
# DRIVER CODE
# =========================

def main():

    # Create products
    laptop = Product("Laptop", 50000)
    mouse = Product("Mouse", 1000)
    keyboard = Product("Keyboard", 2000)

    # Create cart items (with product-level discounts)
    item1 = CartItem(laptop, quantity=1, discount=PercentageDiscount(10))  # 10% off laptop
    item2 = CartItem(mouse, quantity=2)  # no discount
    item3 = CartItem(keyboard, quantity=1, discount=FlatDiscount(200))  # ₹200 off

    # Create cart
    cart = Cart()
    cart.add_item(item1)
    cart.add_item(item2)
    cart.add_item(item3)

    # Apply cart-level coupon
    coupon = MinAmountPercentageCoupon(percent=5, min_amount=20000)
    cart.apply_coupon(coupon)

    # Setup delivery policy
    delivery_policy = DeliveryPolicy(delivery_charge=500, free_above=60000)

    # Calculate price
    calculator = PriceCalculator(delivery_policy)
    bill = calculator.calculate(cart)

    # Print bill
    print("\n===== FINAL BILL =====")
    for key, value in bill.items():
        print(f"{key}: {value:.2f}")


if __name__ == "__main__":
    main()