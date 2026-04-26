from enum import Enum
import heapq
import threading
import time
import uuid


# =========================
# ENUMS
# =========================

class ElevatorState(Enum):
    IDLE = 0
    MOVING = 1


class Direction(Enum):
    UP = 1
    DOWN = -1


class RequestType(Enum):
    EXTERNAL = 1
    INTERNAL = 2


# =========================
# REQUEST
# =========================

class Request:
    def __init__(self, floor: int, request_type: RequestType, direction: Direction = None):
        self.floor = floor
        self.type = request_type
        self.direction = direction


# =========================
# ELEVATOR
# =========================

class Elevator:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.current_floor = 0
        self.state = ElevatorState.IDLE
        self.direction = None

        # SCAN / Elevator Algorithm:
        # - up_heap: min heap (serve upward floors in ascending order)
        # - down_heap: max heap (serve downward floors in descending order)
        self.up_heap = []
        self.down_heap = []

        self.lock = threading.Lock()

        # background processing (simulation)
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.running:
            self.step()
            time.sleep(1)

    def add_request(self, request: Request):
        with self.lock:
            # insert into appropriate direction queue
            if request.floor > self.current_floor:
                heapq.heappush(self.up_heap, request.floor)
            else:
                heapq.heappush(self.down_heap, -request.floor)

            # if idle → initialize direction
            if self.state == ElevatorState.IDLE:
                self.direction = Direction.UP if request.floor > self.current_floor else Direction.DOWN
                self.state = ElevatorState.MOVING

    def step(self):
        with self.lock:
            # no pending requests → idle
            if not self.up_heap and not self.down_heap:
                self.state = ElevatorState.IDLE
                self.direction = None
                return

            # initialize direction if needed
            if self.direction is None:
                self.direction = Direction.UP if self.up_heap else Direction.DOWN

            # =========================
            # SCAN Algorithm (Elevator Algorithm)
            # =========================
            # Serve all requests in current direction
            # then reverse direction

            if self.direction == Direction.UP:
                if self.up_heap:
                    self.current_floor = heapq.heappop(self.up_heap)
                else:
                    self.direction = Direction.DOWN  # reverse

            elif self.direction == Direction.DOWN:
                if self.down_heap:
                    self.current_floor = -heapq.heappop(self.down_heap)
                else:
                    self.direction = Direction.UP  # reverse


# =========================
# SCHEDULER
# =========================

class Scheduler:
    def schedule(self, request: Request, elevators):
        best, min_score = None, float("inf")

        for elevator in elevators:
            score = self._score(elevator, request)
            if score < min_score:
                best, min_score = elevator, score

        if not best:
            raise ValueError("No elevator available")

        best.add_request(request)

    def _score(self, e: Elevator, r: Request):
        with e.lock:
            dist = abs(e.current_floor - r.floor)

            # =========================
            # Nearest Car Algorithm (Dispatch Strategy)
            # =========================

            # idle → best candidate
            if e.state == ElevatorState.IDLE:
                return dist

            # same direction & request lies in path
            if e.direction == r.direction:
                if (r.direction == Direction.UP and e.current_floor <= r.floor) or \
                   (r.direction == Direction.DOWN and e.current_floor >= r.floor):
                    return dist

            # penalty if reversing needed
            return dist + 100


# =========================
# SYSTEM
# =========================

class ElevatorSystem:
    def __init__(self, floors: int):
        self.floors = floors
        self.elevators = {}
        self.scheduler = Scheduler()

    def add_elevator(self, elevator: Elevator):
        self.elevators[elevator.id] = elevator

    def request_elevator(self, floor: int, direction: Direction):
        req = Request(floor, RequestType.EXTERNAL, direction)
        self.scheduler.schedule(req, self.elevators.values())

    def request_inside(self, elevator_id: str, floor: int):
        if elevator_id not in self.elevators:
            raise ValueError("Invalid elevator")

        req = Request(floor, RequestType.INTERNAL)
        self.elevators[elevator_id].add_request(req)


# =========================
# DEMO
# =========================

def main():
    system = ElevatorSystem(10)

    e1, e2 = Elevator(), Elevator()
    system.add_elevator(e1)
    system.add_elevator(e2)

    system.request_elevator(3, Direction.UP)
    system.request_elevator(2, Direction.DOWN)

    time.sleep(10)


if __name__ == "__main__":
    main()