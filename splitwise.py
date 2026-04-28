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


# =========================
# MODELS
# =========================

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


class Group:
    def __init__(self, name, members):
        self.id = str(uuid.uuid4())
        self.name = name
        self.members = set(members)
        self.expenses = {}


# =========================
# STRATEGY
# =========================

class SplitStrategy(ABC):
    @abstractmethod
    def split(self, amount, splits):
        pass


class EqualSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        share = amount / len(splits)
        return [Split(SplitType.EQUAL, s.user_id, share) for s in splits]


class PercentageSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        total = sum(s.percentage for s in splits)
        if total != 100:
            raise ValueError("Invalid percentage")

        return [
            Split(SplitType.PERCENTAGE, s.user_id, (s.percentage / 100) * amount)
            for s in splits
        ]


class ExactSplitStrategy(SplitStrategy):
    def split(self, amount, splits):
        total = sum(s.amount for s in splits)
        if total != amount:
            raise ValueError("Invalid exact split")

        return [Split(SplitType.EXACT, s.user_id, s.amount) for s in splits]


class SplitFactory:
    @staticmethod
    def get_instance(split_type):
        if split_type == SplitType.EQUAL:
            return EqualSplitStrategy()
        elif split_type == SplitType.PERCENTAGE:
            return PercentageSplitStrategy()
        elif split_type == SplitType.EXACT:
            return ExactSplitStrategy()
        else:
            raise ValueError("Unsupported split type")


# =========================
# SERVICES
# =========================

class BalanceService:
    def __init__(self):
        self.balances = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    def update(self, group_id, payer, splits):
        group_balances = self.balances[group_id]

        for split in splits:
            if split.user_id == payer:
                continue

            group_balances[split.user_id][payer] += split.amount
            group_balances[payer][split.user_id] -= split.amount

    def get(self, group_id):
        return self.balances[group_id]


class SimplifyService:
    def simplify(self, balance_map):
        net = defaultdict(float)

        for u in balance_map:
            for v in balance_map[u]:
                net[u] -= balance_map[u][v]
                net[v] += balance_map[u][v]

        creditors, debtors = [], []

        for user, amt in net.items():
            if amt > 0:
                heapq.heappush(creditors, (-amt, user))
            elif amt < 0:
                heapq.heappush(debtors, (amt, user))

        result = []

        while creditors and debtors:
            credit, u1 = heapq.heappop(creditors)
            debit, u2 = heapq.heappop(debtors)

            settle = min(-credit, -debit)
            result.append((u2, u1, settle))

            credit += settle
            debit += settle

            if credit < 0:
                heapq.heappush(creditors, (credit, u1))
            if debit < 0:
                heapq.heappush(debtors, (debit, u2))

        return result


class GroupService:
    def __init__(self):
        self.groups = {}
        self.balance_service = BalanceService()

    def create_group(self, name, members):
        group = Group(name, members)
        self.groups[group.id] = group
        return group

    def add_expense(self, user_id, group_id, req):
        group = self.groups[group_id]

        if user_id not in group.members:
            raise ValueError("User not in group")

        for s in req.splits:
            if s.user_id not in group.members:
                raise ValueError("Invalid participant")

        strategy = SplitFactory.get_instance(req.split_type)
        splits = strategy.split(req.amount, req.splits)

        expense = Expense(req.name, user_id, req.amount)
        expense.splits = splits

        self.balance_service.update(group_id, user_id, splits)
        group.expenses[expense.id] = expense

        return expense

    def get_balances(self, group_id):
        return self.balance_service.get(group_id)


# =========================
# DEMO
# =========================

def main():
    service = GroupService()
    simplify_service = SimplifyService()

    u1, u2, u3 = "U1", "U2", "U3"

    group = service.create_group("Trip", {u1, u2, u3})

    req = ExpenseRequest(
        "Dinner",
        300,
        SplitType.EQUAL,
        [SplitRequest(u1), SplitRequest(u2), SplitRequest(u3)]
    )

    service.add_expense(u1, group.id, req)

    balances = service.get_balances(group.id)
    print("Balances:", balances)

    print("Simplified:", simplify_service.simplify(balances))


if __name__ == "__main__":
    main()