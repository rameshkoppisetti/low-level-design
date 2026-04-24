import uuid
import time
from collections import defaultdict


# =========================
# DOMAIN
# =========================

class Transaction:
    def __init__(self, t_type, amount, counterparty):
        self.type = t_type  # credit / debit
        self.amount = amount
        self.counterparty = counterparty
        self.timestamp = time.time()

    def __str__(self):
        return f"{self.counterparty} {self.type} {self.amount}"


class Wallet:
    def __init__(self, name, balance):
        self.id = str(uuid.uuid4())  # ✅ unique ID
        self.name = name
        self.balance = round(balance, 4)
        self.transactions = []
        self.created_at = time.time()

    def credit(self, amount, from_user):
        self.balance = round(self.balance + amount, 4)
        self.transactions.append(Transaction("credit", amount, from_user))

    def debit(self, amount, to_user):
        if self.balance < amount:
            raise Exception("Insufficient balance")
        self.balance = round(self.balance - amount, 4)
        self.transactions.append(Transaction("debit", amount, to_user))


# =========================
# SERVICE
# =========================

class WalletService:
    def __init__(self):
        self.wallets = {}  # wallet_id → Wallet

    def create_wallet(self, name, balance):
        wallet = Wallet(name, balance)
        self.wallets[wallet.id] = wallet
        print(f"Wallet created: {name} ({wallet.id})")
        return wallet.id

    def get_wallet(self, wallet_id):
        if wallet_id not in self.wallets:
            raise Exception("Invalid wallet")
        return self.wallets[wallet_id]

    def transfer(self, sender_id, receiver_id, amount):
        if amount < 0.0001:
            raise Exception("Minimum amount is 0.0001")

        s = self.get_wallet(sender_id)
        r = self.get_wallet(receiver_id)

        s.debit(amount, r.name)
        r.credit(amount, s.name)

        return s, r

    def overview(self):
        for w in sorted(self.wallets.values(), key=lambda x: x.name):
            print(f"{w.name} {w.balance}")

    def statement(self, wallet_id):
        w = self.get_wallet(wallet_id)
        for t in w.transactions:
            print(t)


# =========================
# OFFER SERVICE
# =========================

class OfferService:
    def __init__(self, wallet_service):
        self.wallet_service = wallet_service

    # Offer1
    def apply_offer1(self, w1, w2):
        if round(w1.balance, 4) == round(w2.balance, 4):
            w1.credit(10, "Offer1")
            w2.credit(10, "Offer1")

    # Offer2
    def apply_offer2(self):
        wallets = list(self.wallet_service.wallets.values())

        wallets.sort(key=lambda w: (
            -len(w.transactions),
            -w.balance,
            w.created_at
        ))

        rewards = [10, 5, 2]

        for i in range(min(3, len(wallets))):
            wallets[i].credit(rewards[i], "Offer2")


# =========================
# CONTROLLER
# =========================

class WalletSystem:
    def __init__(self):
        self.service = WalletService()
        self.offer = OfferService(self.service)

    def execute(self, cmd):
        parts = cmd.split()

        if parts[0] == "CreateWallet":
            return self.service.create_wallet(parts[1], float(parts[2]))

        elif parts[0] == "TransferMoney":
            s, r = self.service.transfer(parts[1], parts[2], float(parts[3]))
            self.offer.apply_offer1(s, r)

        elif parts[0] == "Overview":
            self.service.overview()

        elif parts[0] == "Statement":
            self.service.statement(parts[1])

        elif parts[0] == "Offer2":
            self.offer.apply_offer2()


# =========================
# DEMO
# =========================

def main():
    system = WalletSystem()

    # Create wallets
    h = system.execute("CreateWallet Harry 100")
    r = system.execute("CreateWallet Ron 95.7")
    he = system.execute("CreateWallet Hermione 104")
    a = system.execute("CreateWallet Albus 200")
    d = system.execute("CreateWallet Draco 500")

    print("\n--- Overview ---")
    system.execute("Overview")

    # Transfers
    system.execute(f"TransferMoney {a} {d} 30")
    system.execute(f"TransferMoney {he} {h} 2")
    system.execute(f"TransferMoney {a} {r} 5")

    print("\n--- Overview ---")
    system.execute("Overview")

    print("\n--- Statement Harry ---")
    system.execute(f"Statement {h}")

    print("\n--- Statement Albus ---")
    system.execute(f"Statement {a}")

    # Offer2
    system.execute("Offer2")

    print("\n--- Final Overview ---")
    system.execute("Overview")


if __name__ == "__main__":
    main()