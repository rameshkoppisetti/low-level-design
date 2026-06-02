# BookMyShow LLD

## 1. Requirements

### Functional Requirements

- User can search movies/shows by city, movie, theatre, and date.
- Theatre has multiple screens.
- Screen has a fixed seat layout.
- Movie runs as shows on screens at specific times.
- User can view available seats for a show.
- User can select seats and create a temporary booking/hold.
- Selected seats should be locked for a TTL.
- User can confirm booking by completing payment before TTL expires.
- If payment succeeds, seats become booked.
- If payment fails/cancels/TTL expires, seats become available.
- User can cancel a pending booking.

### Non-Functional Requirements

- Prevent double booking.
- Thread-safe seat reservation.
- Low latency search.
- Booking should be deterministic and idempotent where possible.
- In-memory implementation for interview/demo.
- Extensible for pricing, offers, payments, notifications.

### Out Of Scope

- Real payment gateway.
- Real database.
- Refund handling.
- Seat recommendation.
- User authentication.
- Notifications.

### Edge Cases

- Same seat selected by two users concurrently.
- Duplicate seat ids in one booking request.
- Invalid show id or seat id.
- Booking confirmation after TTL expiry.
- Payment fails after seats are held.
- Cancel already confirmed booking.
- Show timing overlap on same screen.

## 2. APIs / Entry Points

### Public APIs

```text
add_theatre(theatre)
add_screen(theatre_id, screen)
add_show(theatre_id, screen_id, movie, start_time)
search_shows(movie_id=None, city=None, date=None)
get_available_seats(show_id)
create_booking(user_id, show_id, seat_ids) -> booking_id
confirm_booking(booking_id, payment_id) -> bool
cancel_booking(booking_id) -> bool
cleanup_expired_bookings()
```

### Request DTOs

```python
CreateBookingRequest
- user_id
- show_id
- seat_ids

ConfirmBookingRequest
- booking_id
- payment_id
```

### Response DTOs

```python
ShowSearchResult
- show_id
- movie_title
- theatre_name
- screen_name
- city
- start_time

SeatView
- seat_id
- category
- status
- price

BookingResponse
- booking_id
- state
- amount
- expires_at
```

## 3. Entities & Relationships

### Enums

```text
SeatCategory: SILVER, GOLD, VIP
SeatStatus: AVAILABLE, RESERVED, BOOKED
BookingState: PENDING, CONFIRMED, CANCELLED, EXPIRED
PaymentStatus: INITIATED, SUCCESS, FAILED
```

### Entities

`Movie`
- id
- title
- duration

`Theatre`
- id
- name
- city
- screens

`Screen`
- id
- name
- seat layout

`Seat`
- id
- category
- status
- reservation timestamp
- lock

`Show`
- id
- movie
- screen
- start time
- end time
- per-show seats

`Booking`
- id
- user id
- show id
- seats
- amount
- state
- created at

## 4. Class Design

### ShowService

Responsibilities:

- Create shows.
- Prevent overlapping shows on same screen.
- Store shows by screen.

### SearchService

Responsibilities:

- Maintain query indexes.
- Search by movie/city/date.

Useful indexes:

```python
shows_by_movie: Dict[movie_id, List[show_id]]
shows_by_city: Dict[city, List[show_id]]
```

### SeatAvailabilityService

Responsibilities:

- View available seats.
- Reserve selected seats.
- Confirm reserved seats.
- Release reserved seats.

### BookingService

Responsibilities:

- Create booking.
- Calculate amount.
- Reserve seats with TTL.
- Confirm/cancel booking.
- Expire old bookings.

### PricingStrategy

```python
class PricingStrategy:
    def calculate_price(seat_category, is_weekend):
        pass
```

Example:

- Silver = 100
- Gold = 150
- VIP = 250
- Weekend multiplier = 1.25

### PaymentService

Responsibilities:

- Mock payment processing.
- Return success/failure.

## 5. DB Schema

Not needed for in-memory P0.

If persisted:

### movies

```text
id
title
duration_mins
```

### theatres

```text
id
name
city
```

### screens

```text
id
theatre_id
name
```

### seats

```text
id
screen_id
seat_number
category
```

### shows

```text
id
movie_id
screen_id
start_time
end_time
```

### show_seats

```text
show_id
seat_id
status
reserved_by_booking_id
reserved_until
```

### bookings

```text
id
user_id
show_id
state
amount
created_at
confirmed_at
expires_at
```

Indexes:

```text
shows(movie_id, start_time)
theatres(city)
show_seats(show_id, status)
bookings(user_id, created_at)
```

## 6. Core Flow / Pseudocode

### Search Shows

```text
search(movie_id, city)
  get shows from movie index
  filter by city index
  return matching shows
```

### Create Booking

```text
create_booking(show_id, seat_ids)
  validate show
  validate no duplicate seats
  fetch seats
  sort seats by id
  lock seats in sorted order
  recheck all seats are AVAILABLE
  mark seats RESERVED with reservation timestamp
  calculate amount
  create booking as PENDING
  unlock seats
  return booking
```

Why sorted locking:

```text
If two users book overlapping seat sets, sorted lock acquisition avoids deadlock.
```

### Confirm Booking

```text
confirm_booking(booking_id)
  fetch booking
  lock booking
  if booking not PENDING: reject
  if booking expired:
    release seats
    mark EXPIRED
    reject
  lock seats
  recheck all seats are RESERVED
  mark seats BOOKED
  mark booking CONFIRMED
  unlock seats
```

### Cancel Booking

```text
cancel_booking(booking_id)
  fetch booking
  lock booking
  if not PENDING: reject
  lock seats
  release seats
  mark booking CANCELLED
  unlock seats
```

### Expiry Cleanup

```text
cleanup_expired_bookings()
  scan pending bookings
  if booking created_at + ttl < now:
    release seats
    mark EXPIRED
```

## 7. Concurrency

- Each seat has its own lock.
- Booking has its own lock.
- For multi-seat operations, acquire seat locks sorted by seat id.
- Seat status is rechecked after acquiring locks.
- Expired reservations are treated as available.
- Booking confirmation validates TTL again before booking seats.

This prevents:

- double booking
- deadlocks during overlapping seat selection
- confirmation after expiry

## 8. Extensibility

### Patterns

- Strategy Pattern for pricing.
- Repository Pattern for storage.
- Service layer for booking/search/show orchestration.
- State machine for booking lifecycle.

### Future Extensions

- Offers and coupons.
- Payment retries.
- Refunds.
- Seat recommendation.
- Dynamic pricing.
- Waitlist.
- Notifications.
- Distributed locking or DB row locks.

## Interview Line

The critical part is seat concurrency. I keep seat state per show, lock selected seats in sorted order, recheck availability inside the lock, and then reserve them for a TTL. Confirmation books only pending, non-expired reservations. This prevents double booking while keeping unrelated seat bookings concurrent.
