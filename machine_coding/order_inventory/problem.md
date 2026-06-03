# Order and Inventory Management System

## Problem Definition

Design and implement an order and inventory management system for a simple e-commerce platform.

The platform supports:

- sellers
- products
- seller-wise inventory
- one-product orders

Inventory means the number of items of a product in a seller's warehouse.

## Core Requirements

- Products are identified by ids from `0` to `productsCount - 1`.
- Sellers are created with:
  - seller id
  - serviceable pincodes
  - supported payment modes
- Multiple sellers can sell the same product.
- Multiple sellers can deliver to the same pincode.
- Price is irrelevant and assumed same across sellers.
- A buyer selects product and seller while creating an order.
- Each order contains only one product id but one or more units.

## Methods

```text
init(helper, productsCount)
createSeller(sellerId, serviceablePincodes, paymentModes)
addInventory(productId, sellerId, delta) -> "inventory added"
getInventory(productId, sellerId) -> int
createOrder(orderId, destinationPincode, sellerId, productId, productCount, paymentMode) -> str
```

`createOrder` returns one of:

```text
order placed
pincode unserviceable
payment mode not supported
insufficient product inventory
```

## Notes

- Java solution may be tested in a multi-threaded environment.
- Python solution is single-threaded per prompt, but code can still use locks for clarity.
- Use in-memory storage only.

## Sample Flow

```text
init(helper, 10)
createSeller(seller-0, [110001, 560092, 452001, 700001], [netbanking, cash, upi])
createSeller(seller-1, [400050, 110001, 600032, 560092], [netbanking, cash, upi])
addInventory(0, seller-1, 52) -> inventory added
addInventory(0, seller-0, 32) -> inventory added
createOrder(order-1, 400050, seller-1, 0, 5, upi) -> order placed
getInventory(0, seller-1) -> 47
createOrder(order-2, 560092, seller-0, 0, 1, upi) -> order placed
getInventory(0, seller-0) -> 31
```
