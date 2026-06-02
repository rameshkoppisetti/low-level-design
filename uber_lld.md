# Uber / Ride-Hailing System LLD

## 1. Requirements

### Functional Requirements

- Rider can request a ride from pickup to drop location.
- System finds nearby available drivers.
- System estimates fare before booking.
- System assigns one driver to a ride.
- Driver can accept/reject ride.
- Rider can cancel before trip starts.
- Driver can start trip after reaching pickup.
- Driver can complete trip at drop location.
- Payment is collected after trip completion.
- Rider and driver can view ride status.
- Driver can update current location and availability.

### Non-Functional Requirements

- Prevent assigning same driver to two active rides.
- Low-latency driver matching.
- Thread-safe ride assignment.
- Extensible pricing and matching strategies.
- In-memory for LLD/machine-coding demo; production uses DB + cache + event stream.

### Out Of Scope

- Real maps/navigation.
- Real payment gateway.
- Surge pricing ML.
- Fraud detection.
- Multi-stop rides.
- Pool rides.
- Driver onboarding verification.

### Edge Cases

- No driver available.
- Driver rejects ride.
- Rider cancels after driver assignment.
- Driver tries to start ride not assigned to them.
- Payment fails.
- Same driver matched concurrently for two rides.
- Invalid state transition, like completing ride before start.

## 2. APIs / Entry Points

### REST APIs

```text
POST   /riders
POST   /drivers
PATCH  /drivers/{driverId}/location
PATCH  /drivers/{driverId}/availability

POST   /rides/estimate
POST   /rides
PATCH  /rides/{rideId}/accept
PATCH  /rides/{rideId}/reject
PATCH  /rides/{rideId}/cancel
PATCH  /rides/{rideId}/start
PATCH  /rides/{rideId}/complete
GET    /rides/{rideId}
GET    /riders/{riderId}/rides
GET    /drivers/{driverId}/rides
```

### Internal Events

```text
ride-requested
ride-assigned
ride-accepted
ride-cancelled
ride-started
ride-completed
payment-collected
```

### Main Request DTOs

```python
RideRequest
- rider_id
- pickup_location
- drop_location
- cab_type

DriverLocationUpdate
- driver_id
- location

RideActionRequest
- ride_id
- actor_id
```

### Response DTOs

```python
FareEstimate
- distance
- estimated_fare
- estimated_time

RideStatusResponse
- ride_id
- rider_id
- driver_id
- status
- fare
- pickup
- drop
```

## 3. Entities & Relationships

### Enums

```text
RideStatus:
REQUESTED, ASSIGNED, ACCEPTED, STARTED, COMPLETED, CANCELLED, FAILED

DriverStatus:
AVAILABLE, ASSIGNED, ON_TRIP, OFFLINE

CabType:
MINI, SEDAN, SUV

PaymentStatus:
PENDING, SUCCESS, FAILED
```

### Core Entities

`Location`
- latitude
- longitude

`Rider`
- rider_id
- name
- phone

`Driver`
- driver_id
- name
- phone
- cab
- current_location
- status
- lock

`Cab`
- cab_id
- cab_type
- plate_number

`Ride`
- ride_id
- rider_id
- driver_id
- pickup
- drop
- cab_type
- status
- fare
- created_at
- started_at
- completed_at

`Payment`
- payment_id
- ride_id
- amount
- status

### Relationships

```text
Rider 1 -> N Ride
Driver 1 -> N Ride
Driver 1 -> 1 Cab
Ride 1 -> 1 Payment
```

## 4. Class Design

### Layering

```text
Domain Models -> Repositories -> Services -> Controllers / Client Code
```

### Domain

- Rider
- Driver
- Cab
- Ride
- Payment
- Location
- PricingStrategy
- MatchingStrategy
- PaymentModule

### Repositories

`RiderRepository`
- save rider
- get rider

`DriverRepository`
- save driver
- get driver
- list available drivers
- update location/status

`RideRepository`
- save ride
- get ride
- list rides by rider
- list rides by driver

`PaymentRepository`
- save payment
- get payment

### Services

`LocationService`
- calculate distance
- find nearby drivers using driver repository/index

`PricingService`
- estimate fare using pricing strategy

`MatchingService`
- choose best driver using matching strategy

`RideService`
- create ride
- assign driver
- accept/reject/cancel/start/complete ride
- enforce ride state transitions
- handle concurrency around driver assignment

`PaymentService`
- collect payment
- update payment status

### Controllers

`RiderController`
- create rider
- request ride
- cancel ride
- view ride

`DriverController`
- create driver
- update location
- accept/reject ride
- start/complete ride

### Strategies

`MatchingStrategy`

```python
match(ride_request, available_drivers) -> Driver
```

Implementations:

- NearestDriverStrategy
- RatingAwareStrategy
- LoadAwareStrategy

`PricingStrategy`

```python
calculate_fare(distance, cab_type) -> int
```

Implementations:

- BaseFarePricingStrategy
- SurgePricingStrategy

## 5. DB Schema

### riders

```text
id
name
phone
created_at
```

### drivers

```text
id
name
phone
cab_id
status
current_lat
current_lng
created_at
updated_at
```

Indexes:

```text
drivers(status)
drivers(current_lat, current_lng) or geo index
```

### cabs

```text
id
driver_id
cab_type
plate_number
```

### rides

```text
id
rider_id
driver_id
cab_type
pickup_lat
pickup_lng
drop_lat
drop_lng
status
fare
created_at
accepted_at
started_at
completed_at
cancelled_at
```

Indexes:

```text
rides(rider_id, created_at)
rides(driver_id, created_at)
rides(status)
```

### payments

```text
id
ride_id
amount
status
created_at
updated_at
```

## 6. Core Flow / Pseudocode

### Fare Estimate

```text
estimate_fare(rider_id, pickup, drop, cab_type)
  validate rider
  distance = location_service.distance(pickup, drop)
  fare = pricing_strategy.calculate(distance, cab_type)
  return fare
```

### Request Ride

```text
request_ride(rider_id, pickup, drop, cab_type)
  validate rider
  fare = estimate fare
  create ride with REQUESTED
  drivers = find nearby AVAILABLE drivers
  driver = matching_strategy.match(drivers)
  if no driver:
    mark ride FAILED
    return no_driver_available

  lock selected driver
  recheck driver is AVAILABLE
  mark driver ASSIGNED
  assign driver to ride
  mark ride ASSIGNED
  save ride
  publish ride_assigned event
```

### Driver Accept

```text
accept_ride(driver_id, ride_id)
  lock ride
  lock driver
  validate ride assigned to driver
  validate ride status ASSIGNED
  mark ride ACCEPTED
```

### Driver Reject

```text
reject_ride(driver_id, ride_id)
  lock ride
  lock driver
  validate ride assigned to driver
  release driver to AVAILABLE
  mark ride REQUESTED or FAILED
  try assigning next driver
```

### Start Ride

```text
start_ride(driver_id, ride_id)
  validate ride status ACCEPTED
  validate assigned driver
  mark ride STARTED
  mark driver ON_TRIP
```

### Complete Ride

```text
complete_ride(driver_id, ride_id)
  validate ride status STARTED
  collect payment
  if payment success:
    mark ride COMPLETED
    mark driver AVAILABLE
  else:
    mark payment FAILED
    keep ride payment pending or failed
```

### Cancel Ride

```text
cancel_ride(rider_id, ride_id)
  validate rider owns ride
  if ride STARTED or COMPLETED:
    reject cancellation
  if driver assigned:
    mark driver AVAILABLE
  mark ride CANCELLED
```

### Concurrency

Important race:

```text
Two ride requests try to assign same driver.
```

Solution:

```text
lock driver
recheck status is AVAILABLE
mark ASSIGNED inside lock
```

For operations touching both ride and driver:

```text
lock in sorted order by id or use service-level transaction boundary
```

## 7. Extensibility

### Design Patterns

- Strategy Pattern for driver matching.
- Strategy Pattern for pricing.
- Repository Pattern for storage.
- Factory Pattern for cab/pricing/payment strategy selection.
- Observer/Event Pattern for async notifications.

### Future Changes

- Surge pricing.
- Driver ratings.
- Rider cancellation charges.
- Scheduled rides.
- Pool rides.
- Multi-stop rides.
- Geo-index with Redis/Elastic/H3.
- Payment retries.
- Notifications.
- Fraud/risk checks.

## Interview Line

I separate the system into domain models, repositories, services, and controllers. Driver assignment is the critical concurrency point: the matching service finds candidates, but ride service locks the selected driver and rechecks availability before assigning. Pricing and matching are strategies because both are expected to evolve independently.
