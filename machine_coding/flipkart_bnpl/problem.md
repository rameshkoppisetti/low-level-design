# Flipkart Buy Now Pay Later

Implement an in-memory BNPL system that manages users, inventory, orders, and dues.

## APIs

```text
seedInventory(List<String> inventoryLines)
viewInventory() -> List<String>
registerUser(String user, int creditLimit)
buy(String orderId, String user, List<String> itemsWithQuantity, int purchaseDay) -> boolean
clearDues(String user, List<String> orderIdsToClear, int clearingDay)
accountSummary(String user, int asOfDay) -> List<String>
isBlacklisted(String user, int asOfDay) -> boolean
```

## Rules

- Inventory line format: `name,count,price`.
- Duplicate inventory item names merge count and overwrite price.
- Order item format: `name,quantity`.
- Duplicate items inside one order are merged.
- BNPL due day is `purchaseDay + 30`.
- Atomic buy: if any item is invalid, insufficient, user invalid, blacklisted, duplicate order, or credit insufficient, no state changes.
- Available credit is `creditLimit - pendingAmount`.
- A user is blacklisted if 3 or more pending orders are delayed as of the given day.
- Clearing dues sets pending amount to `0` for valid user-owned pending orders.

## Output Formats

Inventory:

```text
name,count,price
```

Account summary:

```text
CREDIT_AVAILABLE,<amount>
ORDER,orderId,purchaseDay,totalAmount,Item1:Q1|Item2:Q2
DUE,orderId,purchaseDay,dueDay,pendingAmount,PENDING|DELAYED,Item1:Q1|Item2:Q2
```
