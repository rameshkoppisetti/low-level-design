import threading


# ---------------- STATE INTERFACE ----------------
class ATMState:
    def insert_card(self, atm, card): print("Invalid operation")
    def enter_pin(self, atm, pin): print("Invalid operation")
    def withdraw(self, atm, amount): print("Invalid operation")
    def deposit(self, atm, amount): print("Invalid operation")
    def eject_card(self, atm): print("Invalid operation")
    def select_transaction(self, atm): print("Invalid operation")
    def check_balance(self, atm): print("Invalid operation")
    def exit(self, atm): print("Invalid operation")


# ---------------- STATES ----------------
class IdleState(ATMState):
    def insert_card(self, atm, card):
        atm.card = card
        print("Card inserted")
        atm.set_state(HasCardState())


class HasCardState(ATMState):
    def enter_pin(self, atm, pin):
        if atm.bank_service.validate(atm.card, pin):
            print("Authenticated")
            atm.account = atm.bank_service.get_account(atm.card)
            atm.set_state(AuthenticatedState())
        else:
            print("Invalid PIN")

    def eject_card(self, atm):
        print("Card ejected")
        atm.reset()


class AuthenticatedState(ATMState):
    def select_transaction(self, atm):
        print("Select transaction")
        atm.set_state(TransactionState())

    def eject_card(self, atm):
        print("Card ejected")
        atm.reset()


class TransactionState(ATMState):
    def withdraw(self, atm, amount):
        account = atm.account

        # Step 1: Check ATM can dispense
        if not atm.dispenser.can_dispense(amount):
            print("ATM cannot dispense this amount")
            return

        # Step 2: Debit via BankService
        if not atm.bank_service.debit(account, amount):
            print("Insufficient balance")
            return

        # Step 3: Dispense
        cash = atm.dispenser.dispense(amount)

        # Step 4: Rollback if failure
        if not cash:
            print("Dispense failed → rollback")
            atm.bank_service.credit(account, amount)
            return

        print("Dispensed:", cash)

    def deposit(self, atm, amount):
        atm.bank_service.credit(atm.account, amount)
        print("Deposited:", amount)

    def check_balance(self, atm):
        balance = atm.bank_service.get_balance(atm.account)
        print("Balance:", balance)

    def exit(self, atm):
        atm.set_state(AuthenticatedState())


# ---------------- ATM ----------------
class ATM:
    def __init__(self, bank_service, dispenser):
        self.bank_service = bank_service
        self.dispenser = dispenser
        self.state = IdleState()
        self.card = None
        self.account = None

    def set_state(self, state):
        self.state = state

    def reset(self):
        self.card = None
        self.account = None
        self.state = IdleState()

    # Delegation
    def insert_card(self, card): self.state.insert_card(self, card)
    def enter_pin(self, pin): self.state.enter_pin(self, pin)
    def withdraw(self, amount): self.state.withdraw(self, amount)
    def deposit(self, amount): self.state.deposit(self, amount)
    def eject_card(self): self.state.eject_card(self)
    def select_transaction(self): self.state.select_transaction(self)
    def check_balance(self): self.state.check_balance(self)
    def exit_transaction(self): self.state.exit(self)


# ---------------- SUPPORT CLASSES ----------------
class Account:
    def __init__(self, balance):
        self.balance = balance
        self.lock = threading.Lock()

    def debit(self, amount):
        with self.lock:
            if self.balance < amount:
                return False
            self.balance -= amount
            return True

    def credit(self, amount):
        with self.lock:
            self.balance += amount


class Card:
    def __init__(self, pin, account):
        self.pin = pin
        self.account = account


class BankService:
    def validate(self, card, pin):
        return card.pin == pin

    def get_account(self, card):
        return card.account

    def debit(self, account, amount):
        return account.debit(amount)

    def credit(self, account, amount):
        account.credit(amount)

    def get_balance(self, account):
        return account.balance


# ---------------- CASH DISPENSER ----------------
class CashDispenser:
    def __init__(self):
        self.notes = {2000: 5, 500: 10, 100: 20}
        self.lock = threading.Lock()

    def can_dispense(self, amount):
        temp = amount
        for note in sorted(self.notes.keys(), reverse=True):
            count = min(temp // note, self.notes[note])
            temp -= count * note
        return temp == 0

    def dispense(self, amount):
        with self.lock:
            if not self.can_dispense(amount):
                return None

            temp = amount
            result = {}

            for note in sorted(self.notes.keys(), reverse=True):
                count = min(temp // note, self.notes[note])
                if count > 0:
                    result[note] = count
                    temp -= note * count

            # Deduct notes
            for note, count in result.items():
                self.notes[note] -= count

            return result


# ---------------- DEMO ----------------
if __name__ == "__main__":
    acc = Account(5000)
    card = Card("1234", acc)

    atm = ATM(BankService(), CashDispenser())

    atm.insert_card(card)
    atm.enter_pin("1234")

    atm.select_transaction()

    atm.withdraw(2700)
    atm.check_balance()

    atm.exit_transaction()
    atm.eject_card()