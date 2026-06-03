# Customer Loyalty Program

Implement an in-memory ecommerce loyalty program.

## APIs

```text
onboard(userName) -> String
purchase(userName, orderAmount, pointsToRedeem, applyDiscount) -> String
getUserStats(userName) -> List<String>
```

## Rules

- Users start with `0` points and `Bronze` level.
- Level is derived from current points:
  - Bronze: `0` to `499`
  - Silver: `500` to `999`
  - Gold: `>= 1000`
- Points are earned on final payable amount.
- Points are fractional and formatted to two decimal places.
- Redemption limits depend on current level at purchase time.
- Personalized discount is a bonus requirement and is intentionally not implemented in this P0 version.
- `applyDiscount` is accepted by the method signature, but discount applied is `0.00`.

## Success Output

```text
PURCHASE_SUCCESS,<pointsRedeemed>,<discountApplied>,<pointsEarned>,<finalPayable>,<currentPoints>,<currentLevel>,<orderCount>
```

## Failure Output

```text
USER_NOT_FOUND
INVALID_ORDER_AMOUNT
INVALID_REDEEM_POINTS
NOT_ENOUGH_POINTS
REDEMPTION_LIMIT_EXCEEDED
```
