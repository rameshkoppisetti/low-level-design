# ---------------- PRODUCT ----------------
class Product:
    def __init__(self, name, price):
        self.name = name
        self.price = price


# ---------------- INVENTORY ----------------
class Inventory:
    def __init__(self):
        self.items = {}

    def add_product(self, product, count):
        self.items[product] = count

    def is_available(self, product):
        return self.items.get(product, 0) > 0

    def deduct(self, product):
        self.items[product] -= 1


# ---------------- STATE INTERFACE ----------------
class State:
    def select_product(self, vm, product):
        print("Invalid action")

    def insert_money(self, vm, amount):
        print("Invalid action")

    def dispense(self, vm):
        print("Invalid action")

    def cancel(self, vm):
        print("Invalid action")


# ---------------- STATES ----------------
class IdleState(State):
    def select_product(self, vm, product):
        if not vm.inventory.is_available(product):
            print("Out of stock")
            return
        vm.selected_product = product
        vm.set_state(HasSelectionState())
        print(f"Selected {product.name}")


class HasSelectionState(State):
    def insert_money(self, vm, amount):
        vm.balance += amount
        print(f"Inserted {amount}, total={vm.balance}")

        if vm.balance >= vm.selected_product.price:
            vm.set_state(HasMoneyState())

    def cancel(self, vm):
        print("Cancelled")
        vm.reset()


class HasMoneyState(State):
    def dispense(self, vm):
        product = vm.selected_product

        vm.inventory.deduct(product)
        change = vm.balance - product.price

        print(f"Dispensed {product.name}")
        if change > 0:
            print(f"Returned change: {change}")

        vm.reset()


# ---------------- VENDING MACHINE ----------------
class VendingMachine:
    def __init__(self):
        self.inventory = Inventory()
        self.state = IdleState()

        self.selected_product = None
        self.balance = 0

    def set_state(self, state):
        self.state = state

    # API
    def select_product(self, product):
        self.state.select_product(self, product)

    def insert_money(self, amount):
        self.state.insert_money(self, amount)

    def dispense(self):
        self.state.dispense(self)

    def cancel(self):
        self.state.cancel(self)

    def reset(self):
        self.selected_product = None
        self.balance = 0
        self.set_state(IdleState())


# ---------------- DEMO ----------------
if __name__ == "__main__":
    vm = VendingMachine()

    coke = Product("Coke", 50)
    chips = Product("Chips", 30)

    vm.inventory.add_product(coke, 5)
    vm.inventory.add_product(chips, 5)

    vm.select_product(coke)
    vm.insert_money(20)
    vm.insert_money(30)
    vm.dispense()