# FlipKar Vehicle Rental Service

## Description

Implement an in-memory vehicle rental service for branches across a city. Customers can rent vehicle types such as SUV, sedan, bike, and hatchback for hourly time slots.

## Core Requirements

- Onboard a new branch with vehicle inventory and hourly prices.
- Add vehicles of an existing type to an existing branch.
- Rent one vehicle for a vehicle type and time slot.
- Default vehicle selection should choose the lowest-price available branch.
- If the cheapest branch has no availability, fallback to the next available branch.
- Bookings must be made before their start time.
- Bookings must be in multiples of 1 hour.
- Show system view for a time slot: blocked and available vehicle types across branches.

## Notes

- Use in-memory data structures only.
- No UI or HTTP API is required.
- Keep selection strategy extensible.
- Use direct service parameters instead of DTOs for interview speed.

