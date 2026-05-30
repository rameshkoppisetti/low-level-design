# ClearFit: Gym Workout Booking Machine Coding Problem

## Context

Cleartrip is launching ClearFit, an enterprise fitness application. Cleartrip is partnering with gyms across Bangalore. Design a backend/console prototype for the beta launch.

## Functional Requirements

### Center Onboarding

- Onboard centers with details like center name, timings, and supported workout variations.
- Each center can have multiple workout variations such as Weights, Cardio, Yoga, Swimming, etc.
- New workout types should be easy to add in the future.

Operations:

- `add_centre(center_name)`
- `add_centre_timings(center_name, timings)`
- `add_centre_activities(center_name, activities)`

### Admin Slot Definition

- A center admin can define workout slots for a center.
- Each workout slot must be within the center's configured timings.
- Each workout slot must use an activity supported by that center.
- Current scope: at one point in time, a center has only one workout.
- Seats in a workout slot are fixed.
- Slots are defined for the same day only and only once.
- Slot update is out of scope.

Operation:

- `add_workout(center_name, workout_type, start_time, end_time, seats)`

### User Operations

- User can optionally register on the platform.
- Authentication is out of scope.
- User can view workout slot availability/unavailability for the day filtered by workout type.
- Results for workout type filter should be sorted by start time ascending.
- User can view workout availability filtered by workout type and center name.
- Results for workout type + center filter should be sorted by seats available ascending.
- User can book a workout slot if seats are available.
- User can cancel a booked workout slot.

Operations:

- `register(user_name)`
- `view_workout_availability(workout_type)`
- `view_workout_availability(workout_type, center_name)`
- `book_session(user_name, center_name, workout_type, start_time, end_time)`
- `cancel_session(user_name, center_name, workout_type, start_time, end_time)`

## Example

```text
AddCentre("Koramangala")
AddCentreTimings("Koramangala", [(6, 9), (18, 21)])
AddCentreActivities("Koramangala", ["Weights", "Cardio", "Yoga", "Swimming"])

AddCentre("Bellandur")
AddCentreTimings("Bellandur", [(7, 10), (19, 22)])
AddCentreActivities("Bellandur", ["Weights", "Cardio", "Yoga"])

addWorkout("Koramangala", "Weights", 6, 7, 100)
addWorkout("Koramangala", "Cardio", 7, 8, 150)
addWorkout("Koramangala", "Yoga", 8, 9, 200)

addWorkout("Bellandur", "Weights", 18, 19, 100)  // invalid timing
addWorkout("Bellandur", "Swimming", 19, 20, 100) // invalid activity
addWorkout("Bellandur", "Cardio", 19, 20, 20)
addWorkout("Bellandur", "Weights", 20, 21, 100)
addWorkout("Bellandur", "Weights", 21, 22, 100)
```

## Expectations

- Code should be demoable.
- Store all data in memory.
- Handle concurrent booking for the same slot correctly.
- Keep design extensible for multiple days later.
- Use integer time for the single-day scope.
- Each entity should have a unique identifier.
- Code should be modular, readable, and testable.

## Folder Structure

```text
machine_coding/clearfit/
  problem.md
  clearfit.py
  test_clearfit.py
```
