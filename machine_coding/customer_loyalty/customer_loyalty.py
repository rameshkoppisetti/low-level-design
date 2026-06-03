from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List


class LoyaltyLevel(Enum):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"


@dataclass(frozen=True)
class LevelRule:
    earn_rate_per_100: float
    max_redeem_percent: float
    max_redeem_points: float


LEVEL_RULES = {
    LoyaltyLevel.BRONZE: LevelRule(10.0, 0.05, 200.0),
    LoyaltyLevel.SILVER: LevelRule(12.5, 0.10, 500.0),
    LoyaltyLevel.GOLD: LevelRule(15.0, 0.15, 1000.0),
}


@dataclass
class User:
    user_name: str
    points: float = 0.0
    level: LoyaltyLevel = LoyaltyLevel.BRONZE
    order_count: int = 0
    total_spent: float = 0.0
    lock: RLock = field(default_factory=RLock, repr=False)


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def create(self, user_name: str) -> bool:
        with self._lock:
            if user_name in self.users:
                return False
            self.users[user_name] = User(user_name)
            return True

    def get(self, user_name: str) -> User | None:
        with self._lock:
            return self.users.get(user_name)


class LoyaltyService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def onboard(self, user_name: str) -> str:
        if not self.user_repo.create(user_name):
            return f"USER_ALREADY_EXISTS,{user_name}"
        return f"ONBOARDED,{user_name}"

    def purchase(
        self,
        user_name: str,
        order_amount: float,
        points_to_redeem: float,
        apply_discount: bool,
    ) -> str:
        user = self.user_repo.get(user_name)
        if not user:
            return "USER_NOT_FOUND"
        if order_amount <= 0:
            return "INVALID_ORDER_AMOUNT"
        if points_to_redeem < 0:
            return "INVALID_REDEEM_POINTS"

        with user.lock:
            order_amount = _round2(order_amount)
            points_to_redeem = _round2(points_to_redeem)

            if points_to_redeem > user.points:
                return "NOT_ENOUGH_POINTS"

            rule = LEVEL_RULES[user.level]
            max_by_percent = _round2(order_amount * rule.max_redeem_percent)
            allowed_redeem = min(user.points, rule.max_redeem_points, max_by_percent)
            if points_to_redeem > allowed_redeem:
                return "REDEMPTION_LIMIT_EXCEEDED"

            amount_after_redemption = _round2(order_amount - points_to_redeem)
            discount_applied = 0.0
            final_payable = _round2(amount_after_redemption - discount_applied)
            points_earned = _round2((final_payable / 100.0) * rule.earn_rate_per_100)

            user.points = _round2(user.points - points_to_redeem + points_earned)
            user.order_count += 1
            user.total_spent = _round2(user.total_spent + final_payable)
            user.level = self._level_for_points(user.points)

            return (
                f"PURCHASE_SUCCESS,{_money(points_to_redeem)},"
                f"{_money(discount_applied)},{_money(points_earned)},"
                f"{_money(final_payable)},{_money(user.points)},"
                f"{user.level.value},{user.order_count}"
            )

    def get_user_stats(self, user_name: str) -> List[str]:
        user = self.user_repo.get(user_name)
        if not user:
            return [f"USER_NOT_FOUND,{user_name}"]

        with user.lock:
            return [
                f"USER,{user.user_name}",
                f"POINTS,{_money(user.points)}",
                f"LEVEL,{user.level.value}",
                f"ORDERS,{user.order_count}",
                f"TOTAL_SPENT,{_money(user.total_spent)}",
            ]

    def _level_for_points(self, points: float) -> LoyaltyLevel:
        if points >= 1000.0:
            return LoyaltyLevel.GOLD
        if points >= 500.0:
            return LoyaltyLevel.SILVER
        return LoyaltyLevel.BRONZE


class EcommerceLoyaltyProgram:
    def __init__(self):
        self.user_repo = UserRepository()
        self.loyalty_service = LoyaltyService(self.user_repo)

    def onboard(self, userName: str) -> str:
        return self.loyalty_service.onboard(userName)

    def purchase(
        self,
        userName: str,
        orderAmount: float,
        pointsToRedeem: float,
        applyDiscount: bool,
    ) -> str:
        return self.loyalty_service.purchase(
            userName,
            orderAmount,
            pointsToRedeem,
            applyDiscount,
        )

    def getUserStats(self, userName: str) -> List[str]:
        return self.loyalty_service.get_user_stats(userName)


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _money(value: float) -> str:
    return f"{_round2(value):.2f}"


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_examples() -> None:
    loyalty = EcommerceLoyaltyProgram()

    assert_equal("ONBOARDED,user1", loyalty.onboard("user1"), "onboard")
    assert_equal(
        "PURCHASE_SUCCESS,0.00,0.00,80.00,800.00,80.00,Bronze,1",
        loyalty.purchase("user1", 800.0, 0.0, False),
        "bronze purchase",
    )
    assert_equal(
        "NOT_ENOUGH_POINTS",
        loyalty.purchase("user1", 4200.0, 100.0, False),
        "not enough points",
    )
    assert_equal(
        "PURCHASE_SUCCESS,0.00,0.00,420.00,4200.00,500.00,Silver,2",
        loyalty.purchase("user1", 4200.0, 0.0, False),
        "reach silver",
    )
    assert_equal(
        "PURCHASE_SUCCESS,300.00,0.00,337.50,2700.00,537.50,Silver,3",
        loyalty.purchase("user1", 3000.0, 300.0, False),
        "silver redeem",
    )
    assert_equal(
        "PURCHASE_SUCCESS,0.00,0.00,625.00,5000.00,1162.50,Gold,4",
        loyalty.purchase("user1", 5000.0, 0.0, False),
        "reach gold",
    )
    assert_equal(
        "PURCHASE_SUCCESS,800.00,0.00,1680.00,11200.00,2042.50,Gold,5",
        loyalty.purchase("user1", 12000.0, 800.0, True),
        "gold redeem without bonus discount",
    )
    assert_equal(
        [
            "USER,user1",
            "POINTS,2042.50",
            "LEVEL,Gold",
            "ORDERS,5",
            "TOTAL_SPENT,23900.00",
        ],
        loyalty.getUserStats("user1"),
        "stats",
    )


def test_invalids_and_redemption_limits() -> None:
    loyalty = EcommerceLoyaltyProgram()

    assert_equal("USER_NOT_FOUND", loyalty.purchase("missing", 100, 0, False), "missing user")
    loyalty.onboard("u1")
    assert_equal("INVALID_ORDER_AMOUNT", loyalty.purchase("u1", 0, 0, False), "invalid amount")
    assert_equal("INVALID_REDEEM_POINTS", loyalty.purchase("u1", 100, -1, False), "invalid redeem")
    assert_equal("NOT_ENOUGH_POINTS", loyalty.purchase("u1", 1000, 1, False), "not enough points")
    loyalty.purchase("u1", 5000, 0, False)
    assert_equal(
        "REDEMPTION_LIMIT_EXCEEDED",
        loyalty.purchase("u1", 100, 11, False),
        "silver percent redemption exceeded",
    )


def run_tests() -> None:
    test_examples()
    test_invalids_and_redemption_limits()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()
