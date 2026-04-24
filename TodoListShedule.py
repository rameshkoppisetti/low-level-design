import threading
import heapq
import time
from datetime import datetime, timedelta
from enum import Enum
import uuid


# ---------------- ENUMS ----------------
class TaskStatus(Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    SCHEDULED = "SCHEDULED"


class ActionType(Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    COMPLETE = "COMPLETE"


# ---------------- MODELS ----------------
class Task:
    def __init__(self, title, deadline=None, tags=None, scheduled_at=None):
        self.id = str(uuid.uuid4())
        self.title = title
        self.deadline = deadline
        self.tags = tags or []
        self.status = TaskStatus.SCHEDULED if scheduled_at else TaskStatus.ACTIVE
        self.created_at = datetime.now()
        self.scheduled_at = scheduled_at


class ActivityLog:
    def __init__(self, action, task_id):
        self.timestamp = datetime.now()
        self.action = action
        self.task_id = task_id


# ---------------- SERVICE ----------------
class TaskService:
    def __init__(self):
        self.tasks = {}
        self.logs = []

        self.lock = threading.Lock()

        # scheduler heap → (scheduled_time, task_id)
        self.schedule_heap = []

        # deadline heap → (deadline, task_id)
        self.deadline_heap = []

        self.condition = threading.Condition(self.lock)

        # background thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def _log(self, action, task_id):
        self.logs.append(ActivityLog(action, task_id))

    # ---------------- ADD ----------------
    def add_task(self, title, deadline=None, tags=None, scheduled_at=None):
        task = Task(title, deadline, tags, scheduled_at)

        with self.condition:
            self.tasks[task.id] = task

            if scheduled_at:
                heapq.heappush(self.schedule_heap, (scheduled_at, task.id))
                self.condition.notify()

            if deadline:
                heapq.heappush(self.deadline_heap, (deadline, task.id))

            self._log(ActionType.ADD, task.id)

        return task.id

    # ---------------- COMPLETE ----------------
    def complete_task(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            task.status = TaskStatus.COMPLETED
            self._log(ActionType.COMPLETE, task_id)
            del self.tasks[task_id]

    # ---------------- GET ACTIVE ----------------
    def get_active_tasks(self):
        with self.lock:
            return [t for t in self.tasks.values() if t.status == TaskStatus.ACTIVE]

    # ---------------- SCHEDULER ----------------
    def _run_scheduler(self):
        while True:
            with self.condition:
                while not self.schedule_heap:
                    self.condition.wait()

                scheduled_time, task_id = self.schedule_heap[0]
                now = datetime.now()

                if scheduled_time > now:
                    wait_time = (scheduled_time - now).total_seconds()
                    self.condition.wait(timeout=wait_time)
                    continue

                # activate task
                heapq.heappop(self.schedule_heap)
                task = self.tasks.get(task_id)
                if task and task.status == TaskStatus.SCHEDULED:
                    task.status = TaskStatus.ACTIVE


# ---------------- STATS ----------------
class StatsService:
    def __init__(self, service: TaskService):
        self.service = service

    def get_stats(self):
        now = datetime.now()

        added = completed = 0
        for log in self.service.logs:
            if log.action == ActionType.ADD:
                added += 1
            elif log.action == ActionType.COMPLETE:
                completed += 1

        # spilled tasks using heap
        spilled = 0
        for deadline, task_id in self.service.deadline_heap:
            task = self.service.tasks.get(task_id)
            if task and deadline < now:
                spilled += 1

        return {
            "added": added,
            "completed": completed,
            "spilled": spilled
        }


# ---------------- DEMO ----------------
if __name__ == "__main__":
    service = TaskService()

    # immediate task
    service.add_task("Learn LLD")

    # scheduled task
    future_time = datetime.now() + timedelta(seconds=3)
    service.add_task("Future Task", scheduled_at=future_time)

    print("Before scheduling:", [t.title for t in service.get_active_tasks()])

    time.sleep(4)

    print("After scheduling:", [t.title for t in service.get_active_tasks()])

    stats = StatsService(service).get_stats()
    print("Stats:", stats)