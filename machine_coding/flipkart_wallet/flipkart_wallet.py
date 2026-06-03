from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock, Thread
from typing import Dict, List, Optional


class TransactionType(Enum):
    LOAD = "LOAD"
    SEND = "SEND"
    RECEIVE = "RECEIVE"


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class Transaction:
    timestamp: int
    transaction_type: TransactionType
    counterparty: str
    amount: int
    sequence: int

    def encode(self) -> str:
        return (
            f"time={self.timestamp}|type={self.transaction_type.value}|"
            f"counterparty={self.counterparty}|amount={self.amount}"
        )


@dataclass
class Wallet:
    user_id: str
    balance: int = 0
    transactions: List[Transaction] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock, repr=False)


class WalletRepository:
    def __init__(self):
        self.wallets: Dict[str, Wallet] = {}
        self._lock = RLock()

    def create(self, user_id: str) -> None:
        with self._lock:
            if user_id in self.wallets:
                raise ValidationError(f"User already exists: {user_id}")
            self.wallets[user_id] = Wallet(user_id)

    def get(self, user_id: str) -> Optional[Wallet]:
        with self._lock:
            return self.wallets.get(user_id)


class WalletService:
    def __init__(self, wallet_repo: WalletRepository):
        self.wallet_repo = wallet_repo
        self._sequence_lock = RLock()
        self._next_sequence = 1

    def load_money(
        self,
        user_id: str,
        amount: int,
        source: str,
        timestamp: int,
    ) -> bool:
        if amount <= 0 or timestamp <= 0 or not source.strip():
            return False

        wallet = self.wallet_repo.get(user_id)
        if not wallet:
            return False

        with wallet.lock:
            wallet.balance += amount
            wallet.transactions.append(
                Transaction(
                    timestamp=timestamp,
                    transaction_type=TransactionType.LOAD,
                    counterparty=source.strip(),
                    amount=amount,
                    sequence=self._next_sequence_number(),
                )
            )
            return True

    def send_money(
        self,
        from_user_id: str,
        to_user_id: str,
        amount: int,
        timestamp: int,
    ) -> bool:
        if amount <= 0 or timestamp <= 0 or from_user_id == to_user_id:
            return False

        sender = self.wallet_repo.get(from_user_id)
        receiver = self.wallet_repo.get(to_user_id)
        if not sender or not receiver:
            return False

        first, second = self._ordered_wallets(sender, receiver)
        with first.lock:
            with second.lock:
                if sender.balance < amount:
                    return False

                sender.balance -= amount
                receiver.balance += amount

                sender.transactions.append(
                    Transaction(
                        timestamp=timestamp,
                        transaction_type=TransactionType.SEND,
                        counterparty=to_user_id,
                        amount=amount,
                        sequence=self._next_sequence_number(),
                    )
                )
                receiver.transactions.append(
                    Transaction(
                        timestamp=timestamp,
                        transaction_type=TransactionType.RECEIVE,
                        counterparty=from_user_id,
                        amount=amount,
                        sequence=self._next_sequence_number(),
                    )
                )
                return True

    def get_balance(self, user_id: str) -> int:
        wallet = self.wallet_repo.get(user_id)
        if not wallet:
            return -1

        with wallet.lock:
            return wallet.balance

    def get_transaction_history(
        self,
        user_id: str,
        sort_by: str,
        filter_by: str,
    ) -> List[str]:
        wallet = self.wallet_repo.get(user_id)
        if not wallet:
            return []

        with wallet.lock:
            transactions = list(wallet.transactions)

        transactions = self._filter_transactions(transactions, filter_by)
        if sort_by == "time":
            transactions = sorted(
                transactions,
                key=lambda transaction: (transaction.timestamp, transaction.sequence),
            )
        elif sort_by == "amount":
            transactions = sorted(
                transactions,
                key=lambda transaction: -transaction.amount,
            )
        else:
            return []

        return [transaction.encode() for transaction in transactions]

    def _filter_transactions(
        self,
        transactions: List[Transaction],
        filter_by: str,
    ) -> List[Transaction]:
        if filter_by == "all":
            return transactions
        if filter_by == "send":
            return [
                transaction
                for transaction in transactions
                if transaction.transaction_type == TransactionType.SEND
            ]
        if filter_by == "receive":
            return [
                transaction
                for transaction in transactions
                if transaction.transaction_type == TransactionType.RECEIVE
            ]
        return []

    def _ordered_wallets(self, first: Wallet, second: Wallet) -> tuple[Wallet, Wallet]:
        if first.user_id <= second.user_id:
            return first, second
        return second, first

    def _next_sequence_number(self) -> int:
        with self._sequence_lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            return sequence


class FlipkartWallet:
    def __init__(self, registeredUserIds: List[str]):
        self.wallet_repo = WalletRepository()
        self.wallet_service = WalletService(self.wallet_repo)

        for user_id in registeredUserIds:
            if user_id.strip():
                self.wallet_repo.create(user_id)

    def loadMoney(
        self,
        userId: str,
        amount: int,
        source: str,
        timestamp: int,
    ) -> bool:
        return self.wallet_service.load_money(userId, amount, source, timestamp)

    def sendMoney(
        self,
        fromUserId: str,
        toUserId: str,
        amount: int,
        timestamp: int,
    ) -> bool:
        return self.wallet_service.send_money(fromUserId, toUserId, amount, timestamp)

    def getBalance(self, userId: str) -> int:
        return self.wallet_service.get_balance(userId)

    def getTransactionHistory(
        self,
        userId: str,
        sortBy: str,
        filterBy: str,
    ) -> List[str]:
        return self.wallet_service.get_transaction_history(userId, sortBy, filterBy)


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_sample_flow() -> None:
    wallet = FlipkartWallet(["user-1", "user-2"])

    assert_equal(True, wallet.loadMoney("user-1", 500, "UPI", 1000), "load money")
    assert_equal(True, wallet.sendMoney("user-1", "user-2", 200, 1010), "send money")
    assert_equal(
        False,
        wallet.sendMoney("user-1", "user-2", 400, 1020),
        "insufficient balance rejected",
    )
    assert_equal(300, wallet.getBalance("user-1"), "sender balance")
    assert_equal(200, wallet.getBalance("user-2"), "receiver balance")
    assert_equal(
        [
            "time=1000|type=LOAD|counterparty=UPI|amount=500",
            "time=1010|type=SEND|counterparty=user-2|amount=200",
        ],
        wallet.getTransactionHistory("user-1", "time", "all"),
        "sender history sorted by time",
    )
    assert_equal(
        ["time=1010|type=RECEIVE|counterparty=user-1|amount=200"],
        wallet.getTransactionHistory("user-2", "time", "receive"),
        "receiver receive history",
    )


def test_sort_by_amount_and_filters() -> None:
    wallet = FlipkartWallet(["user-1", "user-2"])

    wallet.loadMoney("user-1", 500, "UPI", 1000)
    wallet.sendMoney("user-1", "user-2", 200, 1010)
    wallet.loadMoney("user-1", 50, "CreditCard", 1030)

    assert_equal(350, wallet.getBalance("user-1"), "balance after second load")
    assert_equal(
        [
            "time=1000|type=LOAD|counterparty=UPI|amount=500",
            "time=1010|type=SEND|counterparty=user-2|amount=200",
            "time=1030|type=LOAD|counterparty=CreditCard|amount=50",
        ],
        wallet.getTransactionHistory("user-1", "amount", "all"),
        "history sorted by amount",
    )
    assert_equal(
        ["time=1010|type=SEND|counterparty=user-2|amount=200"],
        wallet.getTransactionHistory("user-1", "time", "send"),
        "send filter",
    )


def test_invalid_inputs() -> None:
    wallet = FlipkartWallet(["user-1", "user-2"])

    assert_equal(False, wallet.loadMoney("missing", 100, "UPI", 1), "invalid load user")
    assert_equal(False, wallet.loadMoney("user-1", 0, "UPI", 1), "invalid load amount")
    assert_equal(False, wallet.sendMoney("user-1", "user-2", 1, 1), "insufficient send")
    assert_equal(False, wallet.sendMoney("user-1", "missing", 1, 1), "invalid receiver")
    assert_equal(-1, wallet.getBalance("missing"), "invalid balance user")
    assert_equal([], wallet.getTransactionHistory("missing", "time", "all"), "invalid history user")


def test_concurrent_sends_do_not_overdraw() -> None:
    wallet = FlipkartWallet(["user-1", "user-2", "user-3"])
    wallet.loadMoney("user-1", 100, "UPI", 1)
    results = []

    def send(to_user_id: str) -> None:
        results.append(wallet.sendMoney("user-1", to_user_id, 80, 2))

    first = Thread(target=send, args=("user-2",))
    second = Thread(target=send, args=("user-3",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert_equal([False, True], sorted(results), "only one concurrent send succeeds")
    assert_equal(20, wallet.getBalance("user-1"), "sender not overdrawn")


def run_tests() -> None:
    test_sample_flow()
    test_sort_by_amount_and_filters()
    test_invalid_inputs()
    test_concurrent_sends_do_not_overdraw()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
