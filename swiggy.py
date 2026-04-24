import uuid
from enum import Enum


# =========================
# DOMAIN
# =========================

class MenuItem:
    def __init__(self, name, restaurant_id, description, price, available=True):
        self.id = uuid.uuid4()
        self.restaurant_id = restaurant_id
        self.name = name
        self.description = description
        self.price = price
        self.available = available


class User:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class Restaurant:
    def __init__(self, name):
        self.id = uuid.uuid4()
        self.name = name
        self.menu_items = {}

    def add_item(self, item):
        self.menu_items[item.id] = item

    def get_item(self, item_id):
        return self.menu_items.get(item_id)


class OrderItem:
    def __init__(self, item_id, quantity):
        self.item_id = item_id
        self.quantity = quantity


class Cart:
    def __init__(self, user_id, restaurant_id):
        self.user_id = user_id
        self.restaurant_id = restaurant_id
        self.items = {}

    def add_item(self, item, qty):
        if item.restaurant_id != self.restaurant_id:
            raise ValueError("Different restaurant items not allowed")

        if item.id not in self.items:
            self.items[item.id] = OrderItem(item.id, qty)
        else:
            self.items[item.id].quantity += qty

    def clear(self):
        self.items.clear()


# =========================
# ORDER
# =========================

class OrderStatus(Enum):
    CREATED = 1
    CONFIRMED = 2
    CANCELLED = 3


class Order:
    def __init__(self, user_id, restaurant_id, items, total):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.restaurant_id = restaurant_id
        self.items = items
        self.total = total
        self.status = OrderStatus.CREATED
        self.delivery_partner = None


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


class CardPayment(PaymentStrategy):
    def pay(self, amount):
        print(f"Paid ₹{amount} via Card")
        return True


# =========================
# DELIVERY STRATEGY
# =========================

class DeliveryPartner:
    def __init__(self, id, location):
        self.id = id
        self.location = location
        self.is_available = True


class AssignmentStrategy:
    def assign(self, partners):
        raise NotImplementedError


class NearestDriverStrategy(AssignmentStrategy):
    def assign(self, partners):
        for p in partners:
            if p.is_available:
                p.is_available = False
                return p
        return None


class DeliveryService:
    def __init__(self, partners, strategy):
        self.partners = partners
        self.strategy = strategy

    def assign_partner(self, order):
        return self.strategy.assign(self.partners)


# =========================
# ORDER SERVICE
# =========================

class OrderService:
    def __init__(self, payment_strategy, delivery_service):
        self.orders = {}
        self.restaurants = {}
        self.payment_strategy = payment_strategy
        self.delivery_service = delivery_service

    def add_restaurant(self, restaurant):
        self.restaurants[restaurant.id] = restaurant

    def place_order(self, user, cart):

        restaurant = self.restaurants.get(cart.restaurant_id)
        if not restaurant:
            raise ValueError("Restaurant not found")

        # ---- Validate + calculate ----
        items = []
        total = 0

        for item in cart.items.values():
            menu_item = restaurant.get_item(item.item_id)

            if not menu_item or not menu_item.available:
                raise ValueError("Item not available")

            items.append(OrderItem(item.item_id, item.quantity))
            total += item.quantity * menu_item.price

        # ---- Create order ----
        order = Order(user.id, restaurant.id, items, total)

        # ---- Payment ----
        if not self.payment_strategy.pay(order.total):
            order.status = OrderStatus.CANCELLED
            return order

        # ---- Delivery ----
        partner = self.delivery_service.assign_partner(order)
        order.delivery_partner = partner

        order.status = OrderStatus.CONFIRMED

        # ---- Store ----
        self.orders.setdefault(user.id, {})[order.id] = order

        cart.clear()

        return order

    def get_orders(self, user):
        return self.orders.get(user.id, {}).values()
    

class SearchService:
    def __init__(self, restaurants):
        self.restaurants = restaurants
    
    def add_restaurant(self, restaurant):
        self.restaurants.append(restaurant)
        
    def search_restaurants(self, keyword):
        return [r for r in self.restaurants if keyword.lower() in r.name.lower()]


# =========================
# DEMO
# =========================

def main():
    restaurant = Restaurant("Meghana")
    item = MenuItem("Biryani", restaurant.id, "Good one", 350)
    
    search = SearchService(restaurants=[restaurant])
    res= search.search_restaurants("Meghana")
    print(res[0].name)

    restaurant.add_item(item)

    user = User("u1", "Satya")

    cart = Cart(user.id, restaurant.id)
    cart.add_item(item, 2)

    delivery_service = DeliveryService(
        [DeliveryPartner("d1", "loc1"), DeliveryPartner("d2", "loc2")],
        NearestDriverStrategy()
    )

    order_service = OrderService(
        UpiPayment(),  # strategy
        delivery_service
    )

    order_service.add_restaurant(restaurant)

    order = order_service.place_order(user, cart)

    print(order.id, order.total, order.status)
    print("Assigned:", order.delivery_partner.id)


if __name__ == "__main__":
    main()