from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from enum import Enum
import heapq
import threading
import time
import uuid


class JobRequest:
    def __init__(self, name, task, schedule_type, cron_expr=None):
        self.name = name
        self.task = task
        self.schedule_type = schedule_type
        self.cron_expr = cron_expr


class ScheduleType(Enum):
    HOURLY = 1
    MONTHLY = 2
    WEEKLY = 3
    CRON = 4


class ScheduleStrategy(ABC):
    @abstractmethod
    def next_run_time(self, after_time: datetime):
        pass


class HourlyStrategy(ScheduleStrategy):
    def next_run_time(self, after_time: datetime):
        return after_time + timedelta(hours=1)


class WeeklyStrategy(ScheduleStrategy):
    def __init__(self, weekday=3, hour=10, minute=30):
        self.weekday = weekday
        self.hour = hour
        self.minute = minute

    def next_run_time(self, after_time: datetime):
        days_ahead = (self.weekday - after_time.weekday()) % 7
        candidate = (after_time + timedelta(days=days_ahead)).replace(
            hour=self.hour,
            minute=self.minute,
            second=0,
            microsecond=0,
        )

        if candidate <= after_time:
            candidate += timedelta(days=7)

        return candidate


class MonthlyStrategy(ScheduleStrategy):
    def __init__(self, day=5, hour=10, minute=0):
        self.day = day
        self.hour = hour
        self.minute = minute

    def next_run_time(self, after_time: datetime):
        candidate = datetime(
            after_time.year,
            after_time.month,
            self.day,
            self.hour,
            self.minute,
        )

        if candidate > after_time:
            return candidate

        month = after_time.month + 1
        year = after_time.year
        if month == 13:
            month = 1
            year += 1

        return datetime(year, month, self.day, self.hour, self.minute)


class CronField:
    def __init__(self, expr, min_val, max_val):
        self.values = self.parse(expr, min_val, max_val)

    def parse(self, expr, min_val, max_val):
        result = set()

        for part in expr.split(","):
            if not part:
                raise ValueError("Invalid cron field")

            step = 1
            if "/" in part:
                base, step_expr = part.split("/", 1)
                step = int(step_expr)
                if step <= 0:
                    raise ValueError("Cron step must be positive")
            else:
                base = part

            if base == "*":
                start, end = min_val, max_val
            elif "-" in base:
                start, end = map(int, base.split("-", 1))
            else:
                start = end = int(base)

            if start < min_val or end > max_val or start > end:
                raise ValueError(f"Cron value out of range: {part}")

            result.update(range(start, end + 1, step))

        return result

    def match(self, value):
        return value in self.values


class CronSchedule(ScheduleStrategy):
    def __init__(self, expression):
        if not expression:
            raise ValueError("Cron expression is required")

        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("Invalid cron expression. Expected 5 fields")

        self.minute = CronField(fields[0], 0, 59)
        self.hour = CronField(fields[1], 0, 23)
        self.day = CronField(fields[2], 1, 31)
        self.month = CronField(fields[3], 1, 12)
        self.weekday = CronField(fields[4], 0, 6)

    def next_run_time(self, after_time: datetime):
        next_time = after_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
        max_search_time = next_time + timedelta(days=366 * 5)

        while next_time <= max_search_time:
            if (
                self.minute.match(next_time.minute)
                and self.hour.match(next_time.hour)
                and self.day.match(next_time.day)
                and self.month.match(next_time.month)
                and self.weekday.match(next_time.weekday())
            ):
                return next_time

            next_time += timedelta(minutes=1)

        raise ValueError("No valid cron run time found in next 5 years")


class ScheduleFactory:
    @staticmethod
    def get_instance(schedule_type, cron_expr=None):
        if schedule_type == ScheduleType.HOURLY:
            return HourlyStrategy()
        if schedule_type == ScheduleType.WEEKLY:
            return WeeklyStrategy()
        if schedule_type == ScheduleType.MONTHLY:
            return MonthlyStrategy()
        if schedule_type == ScheduleType.CRON:
            return CronSchedule(cron_expr)

        raise ValueError("Unsupported schedule type")


class Job:
    def __init__(self, name, task, schedule: ScheduleStrategy):
        self.id = str(uuid.uuid4())
        self.name = name
        self.task = task
        self.schedule = schedule


class Task(ABC):
    @abstractmethod
    def execute(self):
        pass


class PrintTask(Task):
    def execute(self):
        print(f"[{datetime.now()}] Executing PrintTask")


class SchedulerEngine:
    def __init__(self, max_workers=5):
        self.jobs = {}
        self.heap = []
        self.lock = threading.Lock()
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.thread = threading.Thread(target=self.start, daemon=True)
        self.thread.start()

    def create_job(self, job_request: JobRequest):
        schedule = ScheduleFactory.get_instance(
            job_request.schedule_type,
            job_request.cron_expr,
        )
        job = Job(job_request.name, job_request.task, schedule)
        run_time = schedule.next_run_time(datetime.now())

        with self.lock:
            self.jobs[job.id] = job
            heapq.heappush(self.heap, (run_time, job.id))

        return job.id

    def start(self):
        while self.running:
            job = None
            wait = 1

            with self.lock:
                while self.heap and self.heap[0][1] not in self.jobs:
                    heapq.heappop(self.heap)

                if self.heap:
                    run_time, job_id = self.heap[0]
                    diff = (run_time - datetime.now()).total_seconds()

                    if diff <= 0:
                        heapq.heappop(self.heap)
                        job = self.jobs.get(job_id)
                        wait = 0
                    else:
                        wait = min(diff, 1)

            if job:
                self.executor.submit(self.run_job, job)

            time.sleep(max(0, wait))

    def run_job(self, job):
        try:
            job.task.execute()
        except Exception as error:
            print(f"Job {job.id} failed: {error}")
        finally:
            self.reschedule(job)

    def reschedule(self, job):
        next_time = job.schedule.next_run_time(datetime.now())

        with self.lock:
            if job.id in self.jobs:
                heapq.heappush(self.heap, (next_time, job.id))

    def cancel_job(self, job_id):
        with self.lock:
            self.jobs.pop(job_id, None)

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        self.executor.shutdown(wait=True)


def main():
    scheduler = SchedulerEngine()

    job1 = JobRequest("job1", PrintTask(), ScheduleType.HOURLY)
    scheduler.create_job(job1)

    job2 = JobRequest(
        "job2",
        PrintTask(),
        ScheduleType.CRON,
        "*/5 * * * *",
    )
    scheduler.create_job(job2)

    time.sleep(5)
    scheduler.stop()


if __name__ == "__main__":
    main()
