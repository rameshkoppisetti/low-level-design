from abc import ABC, abstractmethod


# =========================
# PRODUCT
# =========================

class Product:
    def __init__(self, code, name, price):
        self.code = code
        self.name = name
        self.price = price


# =========================
# INVENTORY ITEM (NEW)
# =========================

class InventoryItem:
    def __init__(self, product: Product, quantity: int):
        self.product = product
        self.quantity = quantity

    def is_available(self):
        return self.quantity > 0

    def deduct(self):
        if self.quantity <= 0:
            raise ValueError("Out of stock")
        self.quantity -= 1


# =========================
# INVENTORY
# =========================

class Inventory:
    def __init__(self):
        self.items = {}  # code -> InventoryItem

    def add_product(self, product: Product, quantity: int):
        self.items[product.code] = InventoryItem(product, quantity)

    def is_available(self, code):
        return code in self.items and self.items[code].is_available()

    def get_item(self, code):
        return self.items.get(code)

    def deduct(self, code):
        if not self.is_available(code):
            raise ValueError("Out of stock")
        self.items[code].deduct()


# =========================
# STATE INTERFACE
# =========================

class State(ABC):

    def select_product(self, vm, code):
        raise ValueError("Invalid action")

    def insert_money(self, vm, amount):
        raise ValueError("Invalid action")

    def dispense(self, vm):
        raise ValueError("Invalid action")

    def cancel(self, vm):
        raise ValueError("Invalid action")


# =========================
# STATES
# =========================

class IdleState(State):

    def select_product(self, vm, code):
        if not vm.inventory.is_available(code):
            raise ValueError("Out of stock")

        vm.selected_item = vm.inventory.get_item(code)
        vm.set_state(vm.has_selection_state)

        print(f"Selected {vm.selected_item.product.name}")


class HasSelectionState(State):

    def insert_money(self, vm, amount):
        vm.balance += amount
        product = vm.selected_item.product

        print(f"Inserted {amount}, total={vm.balance}")

        if vm.balance < product.price:
            print(f"Remaining: {product.price - vm.balance}")
        else:
            vm.set_state(vm.has_money_state)

    def cancel(self, vm):
        print(f"Refund: {vm.balance}")
        vm.reset()


class HasMoneyState(State):

    def dispense(self, vm):
        item = vm.selected_item
        product = item.product

        vm.inventory.deduct(product.code)

        change = vm.balance - product.price

        print(f"Dispensed {product.name}")
        if change > 0:
            print(f"Returned change: {change}")

        vm.reset()


# =========================
# VENDING MACHINE (CONTEXT)
# =========================

class VendingMachine:

    def __init__(self):
        self.inventory = Inventory()

        # reuse state objects (important)
        self.idle_state = IdleState()
        self.has_selection_state = HasSelectionState()
        self.has_money_state = HasMoneyState()

        self.state = self.idle_state

        self.selected_item = None
        self.balance = 0

    def set_state(self, state):
        self.state = state

    def reset(self):
        self.selected_item = None
        self.balance = 0
        self.set_state(self.idle_state)

    # APIs

    def select_product(self, code):
        self.state.select_product(self, code)

    def insert_money(self, amount):
        self.state.insert_money(self, amount)

    def dispense(self):
        self.state.dispense(self)

    def cancel(self):
        self.state.cancel(self)


# =========================
# DEMO
# =========================

def main():
    vm = VendingMachine()

    coke = Product("A1", "Coke", 50)
    chips = Product("A2", "Chips", 30)

    vm.inventory.add_product(coke, 5)
    vm.inventory.add_product(chips, 2)

    vm.select_product("A1")
    vm.insert_money(20)
    vm.insert_money(40)
    vm.dispense()


if __name__ == "__main__":
    main()