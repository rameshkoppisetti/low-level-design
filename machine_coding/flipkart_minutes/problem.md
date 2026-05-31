# Flipkart Minutes: Machine Coding Problem

## Description

Implement the core system for Flipkart Minutes, an instant delivery platform where customers can place orders and delivery partners fulfill them.

## Core Requirements

- Onboard customers and delivery partners.
- Customers can place orders for any item.
- Items are always available; no inventory check is needed.
- Orders are auto-assigned to any available delivery partner.
- If no partner is available, orders wait in a queue.
- Each partner can handle only one order at a time.
- Customers can cancel orders before pickup.
- Canceled orders should not be assigned.
- If an assigned order is canceled before pickup, the partner becomes available for another order.
- Once picked up, an order cannot be canceled.
- Delivery partners can pick up assigned orders and mark them delivered.
- Expose order status and delivery partner status.
- Handle concurrent operations safely.

## Bonus Scope

- Bonus features are intentionally skipped in this implementation to keep the 120-minute solution focused on P0 correctness.
- Optional future additions: notification logs, partner ratings, partner dashboard, and auto-cancel for orders not picked up within 30 minutes.

## Interview Notes

- Use direct service parameters instead of DTOs to keep the solution fast to write.
- Use in-memory repositories.
- Keep assignment logic centralized under a lock because queue, partner availability, and order state must change consistently.
- Use FIFO queues for pending orders and available partners.
