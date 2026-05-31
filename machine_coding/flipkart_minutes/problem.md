# Peer-to-Peer Delivery Platform

## Description

Implement a peer-to-peer delivery system, similar to Dunzo or Swiggy Genie, that can deliver a parcel from one customer to another using available drivers.

## Core Requirements

- Onboard new customers.
- Onboard new drivers.
- The list of deliverable items is preconfigured and fixed in the system.
- Customers can place an order for delivery of a parcel by item id/name.
- Customers can cancel an order before it is picked up.
- One driver can pick up only one order at a time.
- Orders are auto-assigned to available drivers.
- If no driver is available, the system should still accept the order and keep it queued.
- When a driver becomes free, queued orders should be assigned automatically.
- The number of ongoing orders can exceed the number of drivers because orders may wait in queue.
- Once an order is assigned, the assigned driver can pick it up.
- Once picked up, the driver can mark the order as delivered.
- Canceled orders must not be assigned to drivers.
- If an assigned order is canceled before pickup, the driver becomes available for other orders.
- After pickup, an order cannot be canceled by the customer or the system.
- Drivers are assumed to be available 24x7.
- Ignore travel time.
- Expose order status.
- Expose driver status.
- Ensure thread safety for concurrent customer and driver actions.

## Bonus Scope

Bonus features are optional and should be attempted only after finishing P0 features.

- Notify customers and drivers through email/SMS style vendors; for this exercise, simulated vendors may just print logs.
- Allow customers to rate drivers after successful delivery.
- Dashboard to show top drivers using different strategies, such as number of orders or rating.
- Auto-cancel orders if not picked up within 30 minutes of creation, whether queued or assigned.

## Guidelines

- Time: 120 minutes.
- Write modular, clean, demo-able code.
- A driver program, main method, or test case should be available for evaluator-driven examples.
- Use design patterns where they help, but avoid overengineering.
- Handle concurrency where applicable.
- Evaluation criteria:
  - demo-able and functionally correct code
  - readability
  - proper entity modeling
  - modularity and extensibility
  - separation of concerns
  - abstractions
  - exception handling
  - useful comments only where needed
- Use only in-memory data structures.
- Do not use external databases.
- No UX, HTTP API, REST API, or web application is required.
- The application should be standalone.

## Sample Operations

The input/output format is flexible. These examples explain expected behavior in the driver class.

```text
onboard customer(id, name)
onboard driver(id, name)
place order(customer_id, item_id)
cancel order(order_id)
show order status(order_id)
show driver status(driver_id)
pick up order(driver_id, order_id)
complete order(driver_id, order_id)
```

## Implementation Notes

- Use direct service parameters instead of DTOs for interview speed.
- Keep a fixed item catalog in the service or app setup.
- Use in-memory repositories for customers, drivers, and orders.
- Use FIFO queues for pending orders and available drivers.
- Keep assignment logic centralized under a lock because queue state, driver availability, and order state must change consistently.
- Bonus features are intentionally skipped in the current P0 implementation.

