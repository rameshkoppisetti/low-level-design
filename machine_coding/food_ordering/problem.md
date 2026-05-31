# Food Ordering System: Machine Coding Problem

## Description

Implement an online food ordering system.

## Features

- The system has tie-ups with restaurants.
- Each restaurant has a menu with item prices.
- Each restaurant has a maximum item processing capacity at any given time.
- A restaurant will not accept further item requests once its processing capacity is full.
- Once an item/order is fulfilled, the system receives a notification and replenishes the restaurant capacity.
- One or multiple restaurants can be selected for an order based on restaurant selection strategy.
- An order is accepted only if all requested items can be fulfilled by one or more restaurants.

## Requirements

- Onboard a new restaurant with menu and item processing capacity.
- Menu should be reflected in the food ordering system.
- Restaurant should be able to change its menu.
- Customers should be able to place an order by giving item names.
- Assume each item has quantity 1.
- Restaurants should be selected based on the lowest price offered for each item.
- System should track all items served by each restaurant.
- System should expose remaining capacity for each restaurant.
- Once an order is fulfilled, capacity should be replenished for all restaurants involved in that order.

## Sample Driver

```text
add_restaurant("A2B", [Idly: 40, Vada: 30, Paper Plain Dosa: 50], 4)
add_restaurant("Rasaganga", [Idly: 45, Set Dosa: 60, Poori: 25], 6)
add_restaurant("Eat Fit", [Idly: 30, Vada: 40], 2)

order(["Idly", "Poori"])
Output: Order Id#1: Ordered from "Eat Fit" & "Rasaganga"

order(["Idly", "Vada"])
Output: Order Id#2: Ordered from "Eat Fit" & "A2B"

print_stats()
Output:
A2B: 3
Rasaganga: 5
Eat Fit: 0

order(["Idly"])
Output: Ordered from "A2B"

fulfilled_order("Order Id#1")

print_stats()
Output:
A2B: 2
Rasaganga: 6
Eat Fit: 1

fulfilled_order("Order Id#2")

change_menu("Eat Fit", [Idly: 60, Vada: 40], 2)

order(["Idly"])
Output: Ordered from "A2B"
```

## Assumptions

- Restaurant names are unique.
- Item names are case-insensitive for matching.
- Each requested item has quantity 1.
- `fulfilled_order(order_id)` fulfills the whole order and releases capacity for all restaurants assigned to that order.
- If any item cannot be assigned, the entire order is rejected.
- Menu updates replace the previous menu.
- Capacity update changes max capacity and is allowed only if current in-flight item count does not exceed the new capacity.
- All storage is in memory.

## Interview Implementation Notes

- Prefer direct service method parameters in a timed round:
  - `add_restaurant(name, menu, capacity)`
  - `change_menu(name, menu, capacity=None)`
  - `place_order(items)`
- Avoid DTO/request classes unless the interviewer explicitly asks for API-layer modeling.
- DTOs such as `AddRestaurantRequest`, `ChangeMenuRequest`, and `PlaceOrderRequest` are clean in production code, but they add typing and debugging overhead in a 90-minute machine-coding round.
- Spend time on correctness instead: lowest-price allocation, capacity checks, menu updates, fulfillment release, and basic tests.

## Folder Structure

```text
machine_coding/food_ordering/
  problem.md
  food_ordering.py
  test_food_ordering.py
```
