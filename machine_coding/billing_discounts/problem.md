# Billing and Discounts System

## Problem Definition

Design and implement a fully executable, in-memory billing and discounts system for an ecommerce app.

## Core Requirements

- Create a bill for a customer using cart items.
- Compute subtotal.
- Track bill state: open or paid.
- Apply one or more discount codes to an open bill.
- Compute payable amount deterministically.
- When a bill is paid successfully, award loyalty points and update customer level.
- Store everything in memory.
- Generate deterministic sequential bill ids: `B1`, `B2`, `B3`, ...

## Cart Item Format

Each cart item is a string:

```text
itemName|unitPrice|quantity
```

- `itemName` is non-empty and must not contain `|`.
- `unitPrice` is an integer and must be `>= 0`.
- `quantity` is an integer and must be `> 0`.
- Subtotal contribution is `unitPrice * quantity`.

## Supported Discount Codes

- `P10`: 10% off subtotal.
- `P20`: 20% off subtotal.
- `FLAT100`: flat 100 off, only if subtotal `>= 500`.
- `REDEEM`: redeem customer points.

## Discount Rules

- At most one percentage code is effective.
- If both `P10` and `P20` are applied, use the highest percentage.
- `FLAT100` applies at most once and only if subtotal `>= 500`.
- `REDEEM` applies at most once.
- Applying the same code multiple times must not stack.
- Unknown discount code is ignored.

Computation order:

1. Start with subtotal.
2. Apply effective percentage discount.
3. Apply `FLAT100` if applicable.
4. Apply `REDEEM` if applied.

All math must use integers. Percentage discount uses floor division.

## Points and Levels

On successful payment:

- Points earned = `floor(payableAmount / 100)`.
- Points are awarded only if bill transitions to paid.

When `REDEEM` is applied:

- 1 point = 1 dollar discount.
- Redemption amount is capped to 20% of current payable after percentage and flat discounts.
- `redeemCap = floor(currentPayable * 20 / 100)`.
- `redemptionAmount = min(customerPoints, redeemCap)`.
- Points are deducted only if payment succeeds.

Levels:

- `BRONZE`: 0 - 99 points
- `SILVER`: 100 - 499 points
- `GOLD`: 500 - 1999 points
- `PLATINUM`: 2000+ points

## Method Contracts

```text
createBill(customerId, cartItems) -> billId or "ERROR"
applyDiscount(billId, discountCode) -> current payable or -1
payBill(billId, amountPaid) -> receipt or "ERROR"
```

## Expectations

- In-memory only.
- Runnable driver/demo.
- Deterministic output.
- Clean, modular, readable code.
- Proper error handling as specified.
