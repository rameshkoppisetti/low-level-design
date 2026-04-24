from datetime import datetime
from enum import Enum
import uuid


# ---------------- ENUMS ----------------
class TaskStatus(Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


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
        self.status = TaskStatus.ACTIVE
        self.created_at = datetime.now()
        self.scheduled_at = scheduled_at


class ActivityLog:
    def __init__(self, action, task_id):
        self.timestamp = datetime.now()
        self.action = action
        self.task_id = task_id


# ---------------- SERVICES ----------------
class TaskService:
    def __init__(self):
        self.tasks = {}
        self.logs = []

    def _log(self, action, task_id):
        self.logs.append(ActivityLog(action, task_id))

    def add_task(self, title, deadline=None, tags=None, scheduled_at=None):
        task = Task(title, deadline, tags, scheduled_at)
        self.tasks[task.id] = task
        self._log(ActionType.ADD, task.id)
        return task.id

    def update_task(self, task_id, title=None, deadline=None, tags=None):
        task = self.tasks.get(task_id)
        if not task:
            return

        if title:
            task.title = title
        if deadline:
            task.deadline = deadline
        if tags:
            task.tags = tags

        self._log(ActionType.UPDATE, task_id)

    def delete_task(self, task_id):
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._log(ActionType.DELETE, task_id)

    def complete_task(self, task_id):
        task = self.tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.COMPLETED
        self._log(ActionType.COMPLETE, task_id)

        # auto remove
        del self.tasks[task_id]

    def get_active_tasks(self):
        now = datetime.now()
        return [
            t for t in self.tasks.values()
            if not t.scheduled_at or t.scheduled_at <= now
        ]


# ---------------- ACTIVITY SERVICE ----------------
class ActivityService:
    def __init__(self, logs):
        self.logs = logs

    def get_logs(self, start, end):
        return [log for log in self.logs if start <= log.timestamp <= end]


# ---------------- STATS SERVICE ----------------
class StatsService:
    def __init__(self, logs, tasks_snapshot):
        self.logs = logs
        self.tasks_snapshot = tasks_snapshot

    def get_stats(self, start, end):
        added = completed = deleted = 0

        for log in self.logs:
            if start <= log.timestamp <= end:
                if log.action == ActionType.ADD:
                    added += 1
                elif log.action == ActionType.COMPLETE:
                    completed += 1
                elif log.action == ActionType.DELETE:
                    deleted += 1

        # spilled over deadline
        now = datetime.now()
        spilled = sum(
            1 for t in self.tasks_snapshot.values()
            if t.deadline and t.deadline < now
        )

        return {
            "added": added,
            "completed": completed,
            "deleted": deleted,
            "spilled_over": spilled
        }


# ---------------- DEMO ----------------
if __name__ == "__main__":
    service = TaskService()

    t1 = service.add_task("Learn LLD", tags=["coding"])
    t2 = service.add_task("Workout", tags=["health"])

    service.update_task(t1, title="Learn System Design")
    service.complete_task(t2)

    # activity logs
    act_service = ActivityService(service.logs)
    logs = act_service.get_logs(datetime.min, datetime.max)

    print("\n--- Activity Logs ---")
    for log in logs:
        print(log.action, log.task_id)

    # stats
    stats_service = StatsService(service.logs, service.tasks)
    stats = stats_service.get_stats(datetime.min, datetime.max)

    print("\n--- Stats ---")
    print(stats)