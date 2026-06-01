from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, List, Set


class BillStatus(Enum):
    OPEN = "OPEN"
    PAID = "PAID"


class Level(Enum):
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class CartItem:
    item_name: str
    unit_price: int
    quantity: int

    def total(self) -> int:
        return self.unit_price * self.quantity


@dataclass
class Customer:
    customer_id: str
    points: int = 0

    def level(self) -> Level:
        if self.points >= 2000:
            return Level.PLATINUM
        if self.points >= 500:
            return Level.GOLD
        if self.points >= 100:
            return Level.SILVER
        return Level.BRONZE


@dataclass
class Bill:
    bill_id: str
    customer_id: str
    items: List[CartItem]
    subtotal: int
    status: BillStatus = BillStatus.OPEN
    applied_codes: Set[str] = field(default_factory=set)
    final_amount: int = 0
    redeemed_points: int = 0


class CustomerRepository:
    def __init__(self):
        self.customers: Dict[str, Customer] = {}
        self._lock = RLock()

    def get_or_create(self, customer_id: str) -> Customer:
        with self._lock:
            customer = self.customers.get(customer_id)
            if not customer:
                customer = Customer(customer_id)
                self.customers[customer_id] = customer
            return customer


class BillRepository:
    def __init__(self):
        self.bills: Dict[str, Bill] = {}
        self._lock = RLock()

    def save(self, bill: Bill) -> None:
        with self._lock:
            self.bills[bill.bill_id] = bill

    def get(self, bill_id: str) -> Bill | None:
        with self._lock:
            return self.bills.get(bill_id)


class DiscountCalculator:
    VALID_CODES = {"P10", "P20", "FLAT100", "REDEEM"}

    def is_valid_code(self, discount_code: str) -> bool:
        return discount_code in self.VALID_CODES

    def calculate(self, bill: Bill, customer_points: int) -> tuple[int, int]:
        payable = bill.subtotal

        percent = 0
        if "P20" in bill.applied_codes:
            percent = 20
        elif "P10" in bill.applied_codes:
            percent = 10

        payable -= (bill.subtotal * percent) // 100

        if "FLAT100" in bill.applied_codes and bill.subtotal >= 500:
            payable -= 100

        payable = max(0, payable)
        redeemed_points = 0

        if "REDEEM" in bill.applied_codes:
            redeem_cap = (payable * 20) // 100
            redeemed_points = min(customer_points, redeem_cap)
            payable -= redeemed_points

        return max(0, payable), redeemed_points


class BillingService:
    def __init__(
        self,
        customer_repo: CustomerRepository,
        bill_repo: BillRepository,
        discount_calculator: DiscountCalculator,
    ):
        self.customer_repo = customer_repo
        self.bill_repo = bill_repo
        self.discount_calculator = discount_calculator
        self._lock = RLock()
        self._next_bill_number = 1

    def createBill(self, customerId: str, cartItems: List[str]) -> str:
        try:
            if not customerId.strip():
                return "ERROR"
            items = self._parse_cart_items(cartItems)
        except ValidationError:
            return "ERROR"

        with self._lock:
            bill_id = self._next_bill_id_locked()
            subtotal = sum(item.total() for item in items)
            self.customer_repo.get_or_create(customerId.strip())
            self.bill_repo.save(
                Bill(
                    bill_id=bill_id,
                    customer_id=customerId.strip(),
                    items=items,
                    subtotal=subtotal,
                    final_amount=subtotal,
                )
            )
            return bill_id

    def applyDiscount(self, billId: str, discountCode: str) -> int:
        with self._lock:
            bill = self.bill_repo.get(billId)
            if not bill or bill.status != BillStatus.OPEN:
                return -1

            discount_code = discountCode.strip().upper()
            if self.discount_calculator.is_valid_code(discount_code):
                bill.applied_codes.add(discount_code)

            payable, redeemed_points = self._calculate_payable(bill)
            bill.final_amount = payable
            bill.redeemed_points = redeemed_points
            return payable

    def payBill(self, billId: str, amountPaid: int) -> str:
        with self._lock:
            bill = self.bill_repo.get(billId)
            if not bill or bill.status != BillStatus.OPEN:
                return "ERROR"

            payable, redeemed_points = self._calculate_payable(bill)
            if amountPaid != payable:
                return "ERROR"

            customer = self.customer_repo.get_or_create(bill.customer_id)
            customer.points -= redeemed_points
            points_earned = payable // 100
            customer.points += points_earned

            bill.status = BillStatus.PAID
            bill.final_amount = payable
            bill.redeemed_points = redeemed_points

        return (
                f"PAID|final={payable}|pointsEarned={points_earned}|"
                f"totalPoints={customer.points}|level={customer.level().value}"
            )

    def _calculate_payable(self, bill: Bill) -> tuple[int, int]:
        customer = self.customer_repo.get_or_create(bill.customer_id)
        return self.discount_calculator.calculate(bill, customer.points)

    def _parse_cart_items(self, cart_items: List[str]) -> List[CartItem]:
        if not cart_items:
            raise ValidationError("Cart items are required")

        items = []
        for encoded_item in cart_items:
            parts = encoded_item.split("|")
            if len(parts) != 3:
                raise ValidationError("Invalid cart item")

            item_name, unit_price_text, quantity_text = parts
            if not item_name.strip():
                raise ValidationError("Item name is required")

            try:
                unit_price = int(unit_price_text)
                quantity = int(quantity_text)
            except ValueError:
                raise ValidationError("Invalid price or quantity")

            if unit_price < 0 or quantity <= 0:
                raise ValidationError("Invalid price or quantity")

            items.append(CartItem(item_name.strip(), unit_price, quantity))

        return items

    def _next_bill_id_locked(self) -> str:
        bill_id = f"B{self._next_bill_number}"
        self._next_bill_number += 1
        return bill_id


class BillingApp:
    def __init__(self):
        self.customer_repo = CustomerRepository()
        self.bill_repo = BillRepository()
        self.discount_calculator = DiscountCalculator()
        self.billing_service = BillingService(
            self.customer_repo,
            self.bill_repo,
            self.discount_calculator,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_basic_bill_percentage_and_payment() -> None:
    app = BillingApp()
    service = app.billing_service

    bill_id = service.createBill("C1", ["book|200|1", "pen|10|5"])

    assert_equal("B1", bill_id, "first bill id")
    assert_equal(225, service.applyDiscount("B1", "P10"), "P10 payable")
    assert_equal(225, service.applyDiscount("B1", "FLAT100"), "flat not applicable")
    assert_equal(
        "PAID|final=225|pointsEarned=2|totalPoints=2|level=BRONZE",
        service.payBill("B1", 225),
        "payment receipt",
    )


def test_multiple_discounts_and_redeem() -> None:
    app = BillingApp()
    service = app.billing_service

    service.createBill("C1", ["book|200|1", "pen|10|5"])
    service.applyDiscount("B1", "P10")
    service.payBill("B1", 225)

    bill_id = service.createBill("C1", ["shoes|600|1", "tshirt|200|2"])

    assert_equal("B2", bill_id, "second bill id")
    assert_equal(800, service.applyDiscount("B2", "P20"), "P20 payable")
    assert_equal(700, service.applyDiscount("B2", "FLAT100"), "flat applied")
    assert_equal(698, service.applyDiscount("B2", "REDEEM"), "redeem applied")
    assert_equal(
        "PAID|final=698|pointsEarned=6|totalPoints=6|level=BRONZE",
        service.payBill("B2", 698),
        "redeem payment receipt",
    )


def test_invalid_payment_does_not_change_state_or_points() -> None:
    app = BillingApp()
    service = app.billing_service

    bill_id = service.createBill("C2", ["mouse|499|1"])

    assert_equal("B1", bill_id, "bill id")
    assert_equal(450, service.applyDiscount("B1", "P10"), "P10 floor")
    assert_equal("ERROR", service.payBill("B1", 449), "wrong payment rejected")
    assert_equal(
        "PAID|final=450|pointsEarned=4|totalPoints=4|level=BRONZE",
        service.payBill("B1", 450),
        "bill remains open after failed payment",
    )


def test_idempotent_and_highest_percentage() -> None:
    app = BillingApp()
    service = app.billing_service

    service.createBill("C1", ["item|1000|1"])

    assert_equal(900, service.applyDiscount("B1", "P10"), "P10 applied")
    assert_equal(900, service.applyDiscount("B1", "P10"), "P10 idempotent")
    assert_equal(800, service.applyDiscount("B1", "P20"), "highest percent wins")
    assert_equal(700, service.applyDiscount("B1", "FLAT100"), "flat applied once")
    assert_equal(700, service.applyDiscount("B1", "FLAT100"), "flat idempotent")


def test_invalid_inputs_and_paid_bill_rejected() -> None:
    app = BillingApp()
    service = app.billing_service

    assert_equal("ERROR", service.createBill("", ["item|1|1"]), "empty customer rejected")
    assert_equal("ERROR", service.createBill("C1", []), "empty cart rejected")
    assert_equal("ERROR", service.createBill("C1", ["bad"]), "bad item rejected")

    service.createBill("C1", ["item|100|1"])
    assert_equal(100, service.applyDiscount("B1", "UNKNOWN"), "unknown code ignored")
    assert_equal(
        "PAID|final=100|pointsEarned=1|totalPoints=1|level=BRONZE",
        service.payBill("B1", 100),
        "paid",
    )
    assert_equal(-1, service.applyDiscount("B1", "P10"), "paid bill discount rejected")
    assert_equal("ERROR", service.payBill("B1", 100), "double payment rejected")


def run_tests() -> None:
    test_basic_bill_percentage_and_payment()
    test_multiple_discounts_and_redeem()
    test_invalid_payment_does_not_change_state_or_points()
    test_idempotent_and_highest_percentage()
    test_invalid_inputs_and_paid_bill_rejected()


def main() -> None:
    app = BillingApp()
    service = app.billing_service

    print(service.createBill("C1", ["book|200|1", "pen|10|5"]))
    print(service.applyDiscount("B1", "P10"))
    print(service.applyDiscount("B1", "FLAT100"))
    print(service.payBill("B1", 225))

    print(service.createBill("C1", ["shoes|600|1", "tshirt|200|2"]))
    print(service.applyDiscount("B2", "P20"))
    print(service.applyDiscount("B2", "FLAT100"))
    print(service.applyDiscount("B2", "REDEEM"))
    print(service.payBill("B2", 698))

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
