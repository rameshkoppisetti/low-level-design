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

## Expectations

- Functionally correct code for all completed features.
- Create sample data inside the driver program, a test file, or a setup helper.
- Unit tests are useful but not mandatory; the code must at least be demo-able from a main driver.
- Keep the code modular with basic OO design.
- Do not mix unrelated responsibilities into one class.
- Use interfaces/contracts where behavior may change, such as vehicle selection strategy.
- Make the design extensible so new selection strategies or storage implementations can be added without rewriting the codebase.
- Handle edge cases gracefully with clear validation errors.
- Keep the code legible and readable.
- CLI, web application, REST API, and UI are not expected.



## Test cases: 
(Test-cases are defined for understanding feature requirements only. Please model it appropriately based on your service implementation)
add_branch(‘koramangala’, [“1 suv for Rs.12 per hour”, “3 sedan for Rs.10 per hour”, “3 bikes for Rs.20 per hour”]); 
add_branch(‘jayanagar’, [“3 sedan for Rs.11 per hour”, “3 bikes for Rs.30 per hour”, “4 hatchback for Rs.8 per hour”]);
add_branch(‘malleshwaram’, [“1 suv for Rs.11 per hour”, “10 bikes for Rs.3 per hour” , “3 sedan for Rs.10 per hour”]);
add_vehicle(‘koramangala’,  “1 sedan”); //add 1 sedan to koramangala
rent_vehicle(‘suv’, 20th Feb 10:00 AM, 20th Feb 12:00 PM); // should book from malleshwaram.
rent_vehicle(‘suv’, 20th Feb 10:00 AM, 20th Feb 12:00 PM); // should book from koramangala.
rent_vehicle(‘suv’, 20th Feb 10:00 AM, 20th Feb 12:00 PM); //Should fail saying no vehicle.
print_system_view_for_time_slot(20th Feb 11:00 PM, 20th Feb 12:00 PM):
Output:
‘Koramangala’: 
All “suv” are booked.
“sedan” is available for Rs.10
“bike” is available for Rs.20
‘Jayanagar’:
“sedan” is available for Rs.11
“bike” is available for Rs.30
“hatchback” is available for Rs.8
‘‘Malleshwaram’’:
All “suv” are booked.
“bike” is available for Rs.3
“sedan” is available for Rs.10
