import uuid
from enum import Enum


# =========================
# ENUMS
# =========================

class EntryType(Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TxnStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# =========================
# DOMAIN
# =========================

class Account:
    def __init__(self, user_id):
        self.id = str(uuid.uuid4())
        self.user_id = user_id


class Transaction:
    def __init__(self, reference_id):
        self.id = str(uuid.uuid4())
        self.reference_id = reference_id
        self.status = TxnStatus.SUCCESS


class LedgerEntry:
    def __init__(self, account_id, amount, entry_type, txn_id):
        self.id = str(uuid.uuid4())
        self.account_id = account_id
        self.amount = amount
        self.type = entry_type
        self.txn_id = txn_id


# =========================
# SERVICES
# =========================

class LedgerService:
    def __init__(self):
        self.entries = []  # source of truth

    def post_entry(self, entry):
        self.entries.append(entry)

    def get_balance(self, account_id):
        balance = 0
        for e in self.entries:
            if e.account_id == account_id:
                if e.type == EntryType.CREDIT:
                    balance += e.amount
                else:
                    balance -= e.amount
        return balance


class TransactionService:
    def __init__(self, ledger):
        self.ledger = ledger
        self.processed_refs = set()  # idempotency

    def transfer(self, from_acc, to_acc, amount, ref_id):
        if ref_id in self.processed_refs:
            return
        # SELECT balance FROM accounts WHERE id = ? FOR UPDATE;
        # 🔥 compute balance from ledger
        current_balance = self.ledger.get_balance(from_acc.id)
        if current_balance < amount:
            print("Insufficient funds")
            return

        txn = Transaction(ref_id)

        # atomic block (simulate DB txn)
        debit = LedgerEntry(from_acc.id, amount, EntryType.DEBIT, txn.id)
        credit = LedgerEntry(to_acc.id, amount, EntryType.CREDIT, txn.id)

        self.ledger.post_entry(debit)
        self.ledger.post_entry(credit)

        self.processed_refs.add(ref_id)
    
    def withdraw(self, account, amount, ref_id):
        if ref_id in self.processed_refs:
            print("Duplicate txn ignored")
            return

        # 🔥 check balance
        balance = self.ledger.get_balance(account.id)

        if balance < amount:
            print("Insufficient funds")
            return

        txn = Transaction(ref_id)

        # 🔥 double-entry
        debit = LedgerEntry(account.id, amount, EntryType.DEBIT, txn.id)
        credit = LedgerEntry("BANK_CASH", amount, EntryType.CREDIT, txn.id)

        self.ledger.post_entry(debit)
        self.ledger.post_entry(credit)

        self.processed_refs.add(ref_id)

        print("Withdraw successful")
    
    def deposit(self, account, amount, ref_id):
        if ref_id in self.processed_refs:
            return

        txn = Transaction(ref_id)

        debit = LedgerEntry("BANK_CASH", amount, EntryType.DEBIT, txn.id)
        credit = LedgerEntry(account.id, amount, EntryType.CREDIT, txn.id)

        self.ledger.post_entry(debit)
        self.ledger.post_entry(credit)

        self.processed_refs.add(ref_id)


# =========================
# DEMO
# =========================

def main():
    ledger = LedgerService()
    txn_service = TransactionService(ledger)

    acc1 = Account("user1")
    acc2 = Account("user2")

    # deposit initial money (credit)
    ledger.post_entry(LedgerEntry(acc1.id, 1000, EntryType.CREDIT, "init"))

    print("Balance A:", ledger.get_balance(acc1.id))
    print("Balance B:", ledger.get_balance(acc2.id))

    # transfer
    txn_service.transfer(acc1, acc2, 200, "txn1")

    print("Balance A:", ledger.get_balance(acc1.id))
    print("Balance B:", ledger.get_balance(acc2.id))


if __name__ == "__main__":
    main()