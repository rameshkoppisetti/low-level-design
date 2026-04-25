import threading
import uuid

class Product:
    def __init__(self, name, description,price, quantity):
        self.id= str(uuid.uuid4())
        self.name=name
        self.description=description
        self.price= price
        self.quantity=quantity
        self.lock=threading.Lock()
    
    def reserve(self, quantity):
        with self.lock:
            if quantity and quantity<=self.quantity:
                self.quantity-=quantity
            else:
                raise ValueError("Out Of Stock")
    
    def is_available(self, quantity):
        if quantity>0:
            with self.lock:
                return self.quantity>=quantity
                
    
    def unreserve(self, quantity):
        with self.lock:
            self.quantity+=quantity

class InventoryService:
    def __init__(self, products):
        self.products={}
        for prod in products:
            self.add_product(prod)

    def add_product(self, product):
        self.products[product.id]=product
        
    def get_product(self, product_id):
        return self.products.get(product_id)

class User:
    def __init__(self, name):
        self.id= str(uuid.uuid4())
        self.name=name
        
 
class CartItem:
    def __init__(self, product_id, quantity):
        self.id=product_id
        self.quantity=quantity

class Cart:
    def __init__(self, user_id):
        self.id= str(uuid.uuid4())
        self.user_id=user_id
        self.items={} # product_id-> CartItem
        
    def add_to_cart(self, product_id, qty):
        if product_id not in self.items:
            self.items[product_id]= CartItem(product_id, qty)
        else:
            self.items[product_id].quanity+=qty
    
    def remove_from_cart(self, product_id, qty):
        if product_id not in self.items:
            raise ValueError("product does not exist in cart")
        else:
            self.items[product_id].quanity-=qty
            if self.items[product_id].quanity==0:
                del self.items[product_id]
    
    def get_items(self):
        return self.items
    
    def clear(self):
        self.items.clear()
            
class CartService:
    def __init__(self):
        self.carts={}
        
    def get_user_cart(self, user_id):
        return self.carts.get(user_id)

from enum import Enum

class OrderStatus(Enum):
    CREATED=1
    SUCCESS=2
    FAILED=3
    
class OrderItem:
    def __init__(self, product_id, quanity, price):
        self.id=product_id
        self.quanity=quanity
        self.price=price
    
class Order:
    def __init__(self, user, items,total_price):
        self.id= str(uuid.uuid4())
        self.user=user
        self.items=items
        self.status=OrderStatus.CREATED
        self.total_price=total_price
        
    def update_status(self, status):
        self.status=status

class SearchService:
    def __init__(self, products):
        self.products=products
        # indexes=
        self.products_name_index={} # name-> []
        self.generate_search_docs()
    
    def generate_search_docs(self):
        for product in self.products:
            res= self.products_name_index.get(product.name,[])
            res.append(product)
            self.products_name_index[product.name]=res
        
    def search_by_name(self, name):
        return self.products_name_index.get(name, [])

    

from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, order, amount):
        pass

class CreditCardStrategy(PaymentStrategy):
    def pay(self, order, amount):
        return True

class OrderService:
    def __init__(self, inventory: InventoryService, payment_strategy: PaymentStrategy):
        self.orders={} # user_id -> { orders}
        self.inventory= inventory
        self.payment_strategy=payment_strategy
    
    def place_order(self, user, cart):
        items = cart.get_items()
        locked_products = []
        reserved = []

        for pid in sorted(items.keys()):
            product = self.inventory.get_product(pid)
            if not product:
                raise ValueError("Product not found")
            product.lock.acquire()
            locked_products.append(product)

        try:
            total = 0
            for item in items.values():
                product = self.inventory.get_product(item.id)
                if product.quantity < item.quantity:
                    raise ValueError("Insufficient inventory")
                product.quantity -= item.quantity
                reserved.append((product, item.quantity))
                total += product.price * item.quantity

            items_copy = [
                OrderItem(i.id, i.quantity, self.inventory.get_product(i.id).price)
                for i in items.values()
            ]
            order = Order(user, items_copy, total)

            ok = self.payment_strategy.pay(order, total)
            if ok:
                order.update_status(OrderStatus.SUCCESS)
            else:
                for p, q in reserved:
                    p.quantity += q
                order.update_status(OrderStatus.FAILED)

            self.orders.setdefault(user.id, {})[order.id] = order
            return order
        finally:
            for p in reversed(locked_products):
                p.lock.release()


def main():
    # global product repo
    products = [Product("Phone","phone goat", 100, 5),Product("Laptop", "goat laptop", 500, 3)]
    search_service = SearchService(products)
    results=search_service.search_by_name("Phone")
    print(results)
    user= User("satya")

    cart = Cart("user1")
    cart.add_to_cart(products[0].id, 2)
    cart.add_to_cart(products[1].id, 1)
    inv_service=InventoryService(products)

    service = OrderService(inv_service,CreditCardStrategy())

    order = service.place_order(user,cart)

    print("Order status:", order.status)
    print("Remaining inventory:", products[0], products[1])


if __name__ == "__main__":
    main()