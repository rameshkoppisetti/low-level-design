from abc import ABC, abstractmethod
from collections import defaultdict
import heapq
import uuid
import enum


# =========================
# ENUM
# =========================

class SplitType(enum.Enum):
    EQUAL = 1
    PERCENTAGE = 2
    EXACT = 3


# =========================
# DTOs
# =========================

class SplitRequest:
    def __init__(self, user_id, percentage=None, amount=None):
        self.user_id = user_id
        self.percentage = percentage
        self.amount = amount


class ExpenseRequest:
    def __init__(self, name, amount, split_type, splits):
        self.name = name
        self.amount = amount
        self.split_type = split_type
        self.splits = splits


class SettlementRequest:
    def __init__(self, paid_by, paid_to, amount):
        self.paid_by = paid_by
        self.paid_to = paid_to
        self.amount = amount


# =========================
# MODELS
# =========================

class User:
    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name


class Split:
    def __init__(self, split_type, user_id, amount):
        self.id = str(uuid.uuid4())
        self.type = split_type
        self.user_id = user_id
        self.amount = amount


class Expense:
    def __init__(self, name, paid_by, amount):
        self.id = str(uuid.uuid4())
        self.name = name
        self.paid_by = paid_by
        self.amount = amount
        self.splits = []


class Settlement:
    def __init__(self, paid_by, paid_to, amount):
        self.id = str(uuid.uuid4())
        self.paid_by = paid_by
        self.paid_to = paid_to
        self.amount = amount


# =========================
# STRATEGY
# =========================

class SplitStrategy(ABC):
    @abstractmethod
    def split(self, amount, splits):
        pass


class EqualSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        if not splits:
            raise ValueError("Splits cannot be empty")

        share = amount / len(splits)

        return [
            Split(SplitType.EQUAL, s.user_id, share)
            for s in splits
        ]


class PercentageSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        total_percentage = sum(s.percentage for s in splits)

        if total_percentage != 100:
            raise ValueError("Invalid percentage split")

        return [
            Split(
                SplitType.PERCENTAGE,
                s.user_id,
                amount * s.percentage / 100
            )
            for s in splits
        ]


class ExactSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        total_amount = sum(s.amount for s in splits)

        if total_amount != amount:
            raise ValueError("Invalid exact split")

        return [
            Split(SplitType.EXACT, s.user_id, s.amount)
            for s in splits
        ]


# =========================
# FACTORY
# =========================

class SplitFactory:
    @staticmethod
    def get_instance(split_type):
        if split_type == SplitType.EQUAL:
            return EqualSplitStrategy()

        if split_type == SplitType.PERCENTAGE:
            return PercentageSplitStrategy()

        if split_type == SplitType.EXACT:
            return ExactSplitStrategy()

        raise ValueError("Unsupported split type")


# =========================
# REPOSITORIES
# =========================

class UserRepository:
    def __init__(self):
        self.users = {}

    def save(self, user):
        self.users[user.id] = user

    def get(self, user_id):
        return self.users.get(user_id)

    def exists(self, user_id):
        return user_id in self.users


class ExpenseRepository:
    def __init__(self):
        self.expenses = {}

    def save(self, expense):
        self.expenses[expense.id] = expense

    def get_all(self):
        return list(self.expenses.values())


class SettlementRepository:
    def __init__(self):
        self.settlements = {}

    def save(self, settlement):
        self.settlements[settlement.id] = settlement


# =========================
# BALANCE SERVICE
# =========================

class BalanceService:
    def __init__(self):
        # balances[A][B] > 0 means A owes B
        self.balances = defaultdict(lambda: defaultdict(float))

    def update_for_expense(self, payer, splits):
        for split in splits:
            user_id = split.user_id

            if user_id == payer:
                continue

            # user_id owes payer
            self._add_balance(user_id, payer, split.amount)

    def _add_balance(self, from_user, to_user, amount):
        """
        from_user owes to_user amount.
        If reverse balance exists, simplify it.
        """

        reverse_amount = self.balances[to_user][from_user]

        if reverse_amount > 0:
            if reverse_amount > amount:
                self.balances[to_user][from_user] -= amount
            elif reverse_amount == amount:
                self.balances[to_user][from_user] = 0
            else:
                remaining = amount - reverse_amount
                self.balances[to_user][from_user] = 0
                self.balances[from_user][to_user] += remaining
        else:
            self.balances[from_user][to_user] += amount

    def settle(self, paid_by, paid_to, amount):
        """
        paid_by pays paid_to.
        So paid_by's debt to paid_to reduces.
        """

        current = self.balances[paid_by][paid_to]

        if current <= 0:
            raise ValueError("No outstanding balance")

        if amount > current:
            raise ValueError("Cannot settle more than owed")

        self.balances[paid_by][paid_to] -= amount

        if self.balances[paid_by][paid_to] == 0:
            del self.balances[paid_by][paid_to]

    def get_user_balances(self, user_id):
        result = []

        for to_user, amount in self.balances[user_id].items():
            if amount > 0:
                result.append((user_id, to_user, amount))

        for from_user in self.balances:
            amount = self.balances[from_user].get(user_id, 0)
            if amount > 0:
                result.append((from_user, user_id, amount))

        return result

    def show_balances(self):
        for from_user in self.balances:
            for to_user in self.balances[from_user]:
                amount = self.balances[from_user][to_user]
                if amount > 0:
                    print(from_user, "owes", to_user, "=", amount)


# =========================
# SIMPLIFY SERVICE
# =========================

class SimplifyService:
    def simplify(self, balance_map):
        net = defaultdict(float)

        for u in balance_map:
            for v in balance_map[u]:
                amount = balance_map[u][v]

                if amount > 0:
                    net[u] -= amount
                    net[v] += amount

        creditors = []
        debtors = []

        for user, amount in net.items():
            if amount > 0:
                heapq.heappush(creditors, (-amount, user))
            elif amount < 0:
                heapq.heappush(debtors, (amount, user))

        result = []

        while creditors and debtors:
            credit_amount, creditor = heapq.heappop(creditors)
            debit_amount, debtor = heapq.heappop(debtors)

            credit_amount = -credit_amount
            debit_amount = -debit_amount

            settled = min(credit_amount, debit_amount)

            result.append((debtor, creditor, settled))

            credit_amount -= settled
            debit_amount -= settled

            if credit_amount > 0:
                heapq.heappush(creditors, (-credit_amount, creditor))

            if debit_amount > 0:
                heapq.heappush(debtors, (-debit_amount, debtor))

        return result


# =========================
# EXPENSE SERVICE
# =========================

class ExpenseService:
    def __init__(self, user_repo, expense_repo, balance_service):
        self.user_repo = user_repo
        self.expense_repo = expense_repo
        self.balance_service = balance_service

    def add_expense(self, paid_by, req):
        if not self.user_repo.exists(paid_by):
            raise ValueError("Payer does not exist")

        for split_req in req.splits:
            if not self.user_repo.exists(split_req.user_id):
                raise ValueError("Invalid split user")

        strategy = SplitFactory.get_instance(req.split_type)
        splits = strategy.split(req.amount, req.splits)

        expense = Expense(req.name, paid_by, req.amount)
        expense.splits = splits

        self.expense_repo.save(expense)

        self.balance_service.update_for_expense(paid_by, splits)

        return expense


# =========================
# SETTLEMENT SERVICE
# =========================

class SettlementService:
    def __init__(self, settlement_repo, balance_service):
        self.settlement_repo = settlement_repo
        self.balance_service = balance_service

    def settle(self, req):
        self.balance_service.settle(
            req.paid_by,
            req.paid_to,
            req.amount
        )

        settlement = Settlement(
            req.paid_by,
            req.paid_to,
            req.amount
        )

        self.settlement_repo.save(settlement)

        return settlement


# =========================
# DEMO
# =========================

def main():
    user_repo = UserRepository()
    expense_repo = ExpenseRepository()
    settlement_repo = SettlementRepository()

    balance_service = BalanceService()
    expense_service = ExpenseService(
        user_repo,
        expense_repo,
        balance_service
    )
    settlement_service = SettlementService(
        settlement_repo,
        balance_service
    )
    simplify_service = SimplifyService()

    # ===== USERS =====
    u1 = User("Satya")
    u2 = User("Rahul")
    u3 = User("Amit")

    user_repo.save(u1)
    user_repo.save(u2)
    user_repo.save(u3)

    # ===== EXPENSE 1: EQUAL =====
    req1 = ExpenseRequest(
        name="Dinner",
        amount=300,
        split_type=SplitType.EQUAL,
        splits=[
            SplitRequest(u1.id),
            SplitRequest(u2.id),
            SplitRequest(u3.id)
        ]
    )

    expense_service.add_expense(u1.id, req1)

    print("---- Balances after Expense 1 ----")
    balance_service.show_balances()

    # ===== EXPENSE 2: EXACT =====
    req2 = ExpenseRequest(
        name="Cab",
        amount=300,
        split_type=SplitType.EXACT,
        splits=[
            SplitRequest(u1.id, amount=100),
            SplitRequest(u2.id, amount=100),
            SplitRequest(u3.id, amount=100)
        ]
    )

    expense_service.add_expense(u2.id, req2)

    print("\n---- Balances after Expense 2 ----")
    balance_service.show_balances()

    # ===== SETTLEMENT =====
    settlement_req = SettlementRequest(
        paid_by=u3.id,
        paid_to=u1.id,
        amount=100
    )

    settlement_service.settle(settlement_req)

    print("\n---- Balances after Settlement ----")
    balance_service.show_balances()

    # ===== SIMPLIFY =====
    print("\n---- Simplified Debts ----")
    simplified = simplify_service.simplify(balance_service.balances)

    for debtor, creditor, amount in simplified:
        print(debtor, "pays", creditor, "=", amount)


if __name__ == "__main__":
    main()