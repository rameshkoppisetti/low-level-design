# Elevator System LLD

## 1. Requirements

### Functional Requirements

- Building has multiple floors and multiple elevators.
- User can request an elevator from a floor with direction: `UP` or `DOWN`.
- User inside elevator can request a destination floor.
- System assigns an elevator to external requests.
- Elevator should move, stop at requested floors, open/close door, and continue.
- Elevator should support multiple pending requests.
- Elevator should serve requests using a direction-aware algorithm such as SCAN.
- System should expose current elevator status.
- System should support cancel/shutdown in simulation.

### Non-Functional Requirements

- Thread-safe request handling.
- Low latency assignment for new requests.
- Avoid starvation.
- Extensible to new dispatch strategies.
- In-memory simulation is enough.

### Out Of Scope

- Real hardware integration.
- Emergency/fire mode.
- Weight sensor.
- Door obstruction sensor.
- Destination control grouping.
- Persistent storage.

### Edge Cases

- Request for invalid floor.
- Multiple users request the same floor.
- Elevator is idle.
- Elevator is moving in same direction and request is on the way.
- Elevator is moving away from request.
- All elevators are busy.
- Internal request for current floor.

## 2. APIs / Entry Points

### Public APIs

```text
add_elevator(elevator_id, initial_floor)
request_elevator(floor, direction) -> elevator_id
request_inside(elevator_id, destination_floor)
get_elevator_status(elevator_id)
step() / start() / stop()
```

### Request DTOs

```python
ElevatorRequest
- floor
- request_type: EXTERNAL / INTERNAL
- direction: UP / DOWN / None
```

### Response DTOs

```python
ElevatorStatus
- elevator_id
- current_floor
- direction
- state
- pending_up_requests
- pending_down_requests
```

## 3. Entities & Relationships

### Enums

```text
Direction: UP, DOWN
ElevatorState: IDLE, MOVING, DOOR_OPEN
RequestType: EXTERNAL, INTERNAL
```

### Entities

`ElevatorRequest`
- Represents external hall call or internal destination request.

`Elevator`
- Has id, current floor, direction, state.
- Maintains pending requests.
- Executes movement using SCAN.

`ElevatorSystem`
- Owns elevators.
- Validates requests.
- Delegates assignment to scheduler.

`Scheduler`
- Chooses best elevator for external request.

## 4. Class Design

### ElevatorSystem

Responsibilities:

- Validate floor.
- Register elevators.
- Accept external and internal requests.
- Delegate external request assignment.
- Expose elevator status.

### Elevator

Responsibilities:

- Store pending up/down requests.
- Move according to current direction.
- Serve floors.
- Maintain current state.

### Scheduler Interface

```python
class ElevatorScheduler:
    def schedule(request, elevators) -> Elevator:
        pass
```

### NearestCarScheduler

Uses score:

```text
idle elevator: distance
same direction and request on path: distance
otherwise: distance + penalty
```

### Request Queues

For SCAN:

```text
up_heap: min heap for upward floors
down_heap: max heap for downward floors
```

This allows:

- upward requests served in ascending order
- downward requests served in descending order

## 5. DB Schema

No DB required for P0.

If persisted:

### elevators

```text
id
current_floor
state
direction
updated_at
```

### elevator_requests

```text
id
elevator_id
source_floor
destination_floor
request_type
direction
status
created_at
completed_at
```

Indexes:

```text
elevator_requests(elevator_id, status)
elevator_requests(status, created_at)
```

## 6. Core Flow / Pseudocode

### External Request

```text
request_elevator(floor, direction)
  validate floor
  create external request
  scheduler selects best elevator
  selected_elevator.add_request(request)
  return elevator_id
```

### Internal Request

```text
request_inside(elevator_id, destination_floor)
  validate elevator
  validate floor
  create internal request
  elevator.add_request(request)
```

### Elevator Step

```text
step()
  if no requests:
    state = IDLE
    direction = None
    return

  if direction is None:
    choose direction based on available queues

  if direction == UP:
    if up_heap has requests:
      move to next smallest up floor
      serve floor
    else:
      direction = DOWN

  if direction == DOWN:
    if down_heap has requests:
      move to next largest down floor
      serve floor
    else:
      direction = UP
```

### Concurrency

- Each elevator has its own lock.
- ElevatorSystem has a lock for elevator map.
- Scheduler reads elevator state under elevator locks.
- Elevator movement and request insertion are protected by elevator lock.

### Failure Cases

- Invalid floor: raise validation error.
- Invalid elevator id: raise not found error.
- No elevator registered: reject request.

## 7. Extensibility

### Design Patterns

- Strategy Pattern: elevator assignment strategy.
- Repository-like map: elevator storage.
- Command/Request object: external/internal elevator requests.

### Future Extensions

- Add priority requests.
- Add emergency mode.
- Add maintenance mode.
- Add capacity checks.
- Add real-time floor-by-floor simulation.
- Add destination dispatch strategy.
- Add metrics: average wait time, elevator utilization.

## Interview Line

I use SCAN inside each elevator to serve floors in one direction before reversing, which reduces unnecessary direction changes. For assigning external calls, I use a scheduler strategy so the system can start with nearest-car assignment and later switch to load-aware or destination-aware dispatch without changing elevator internals.
