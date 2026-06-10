# FlipFit

Design an in-memory backend system for FlipFit.

## Requirements

- Add centers with city, location, latitude, longitude.
- Add workout types at center level.
- Add/delete workout slots for a center, workout type, day, start time, seats, and waitlist size.
- Slots can overlap.
- View workouts available/unavailable for a day at a center.
- Register users.
- Book a workout for a user.
- A user can book at most 3 slots in a day.
- If seats are full, add the user to a fixed-size waitlist.
- On cancellation, promote the first eligible waitlisted user and notify users.
- View user bookings for a day.
- Recommend up to 3 slots for the same workout type in same/nearby centers by ranking type:
  - `TIME`
  - `DISTANCE`

## Assumptions

- Storage is in-memory.
- Time is represented as minutes from midnight, e.g. `360` for 6:00 AM, `390` for 6:30 AM.
- Day is a string such as `MONDAY` or `2026-06-03`.
- Bonus/multi-city production concerns are not coded beyond storing city/location fields.
- Notifications are printed and stored in memory for tests.
