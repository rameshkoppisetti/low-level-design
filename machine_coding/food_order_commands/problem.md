# Food Order Management System Using Commands

## Problem Definition

Implement a simplified food order management system.

The system supports:

- add restaurant
- update restaurant menu
- place order
- dispatch order
- query served item counts
- query dispatched orders

All operations are provided as encoded command strings.

## Command Processing

```text
processCommands(commands: List[str]) -> List[str]
```

- Each command parameter is separated by `|`.
- Each command starts with numeric timestamp.
- Commands must execute in increasing timestamp order.
- If timestamps are equal, preserve original input order.
- Return one output per input command.
- Outputs must align with original input positions.

## Commands

### Add Restaurant

```text
timestamp|ADD_RESTAURANT|restaurantId|capacity|menu
```

`menu` format:

```text
item:price,item:price
```

Output:

```text
OK
RESTAURANT_ALREADY_EXISTS
```

### Update Menu

```text
timestamp|UPDATE_MENU|restaurantId|menuUpdates
```

- If price `>= 0`, upsert item.
- If price `< 0`, remove item.
- Items not mentioned remain unchanged.

Output:

```text
OK
RESTAURANT_NOT_FOUND
```

### Place Order

```text
timestamp|PLACE_ORDER|orderId|customerId|strategy|items
```

Strategies:

- `LOWEST_TOTAL_PRICE`
- `MAX_REMAINING_CAPACITY`

Output:

```text
ACCEPTED
REJECTED
INVALID_STRATEGY
```

### Dispatch Order

```text
timestamp|DISPATCH_ORDER|orderId
```

Output:

```text
DISPATCHED
INVALID_ORDER
ALREADY_DISPATCHED
```

## Queries

### Get Items Served Per Restaurant

```text
getRestaurantItemCounts() -> List[str]
```

Output row:

```text
restaurantId|itemName|count
```

Rows sorted lexicographically ascending.

### Get Dispatched Orders

```text
getDispatchedOrders(restaurantId: str) -> List[str]
```

Output row:

```text
dispatchTimestamp|orderId|customerId|items
```

Rows returned in exact dispatch order.
