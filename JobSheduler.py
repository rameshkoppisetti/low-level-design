from abc import ABC, abstractmethod
import datetime
from enum import Enum
import heapq
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor


# =========================
# REQUEST
# =========================
class JobRequest:
    def __init__(self, name, task, schedule_type):
        self.name = name
        self.task = task
        self.schedule_type = schedule_type


# =========================
# ENUM
# =========================
class ScheduleType(Enum):
    HOURLY = 1
    WEEKLY = 2
    MONTHLY = 3

# =========================
# STRATEGY
# =========================
class ScheduleStrategy(ABC):
    @abstractmethod
    def next_run_time(self, time):
        pass


class HourlyStrategy(ScheduleStrategy):
    def next_run_time(self, time):
        return time + datetime.timedelta(hours=1)


class WeeklyStrategy(ScheduleStrategy):
    def __init__(self, weekday=3, hour=10, minute=30):  # Thursday
        self.weekday = weekday
        self.hour = hour
        self.minute = minute

    def next_run_time(self, time):
        next_time = time
        while True:
            next_time += datetime.timedelta(days=1)
            if next_time.weekday() == self.weekday:
                return next_time.replace(hour=self.hour, minute=self.minute)


class MonthlyStrategy(ScheduleStrategy):
    def __init__(self, day=5, hour=10, minute=0):
        self.day = day
        self.hour = hour
        self.minute = minute

    def next_run_time(self, time):
        month = time.month + 1 if time.day >= self.day else time.month
        year = time.year + (month // 12)
        month = month % 12 or 12
        return datetime.datetime(year, month, self.day, self.hour, self.minute)


# =========================
# FACTORY
# =========================
class ScheduleFactory:
    @staticmethod
    def get_instance(type):
        if type == ScheduleType.HOURLY:
            return HourlyStrategy()
        if type == ScheduleType.WEEKLY:
            return WeeklyStrategy()
        if type == ScheduleType.MONTHLY:
            return MonthlyStrategy()


# =========================
# JOB
# =========================
class Job:
    def __init__(self, name, task, schedule: ScheduleStrategy):
        self.id = str(uuid.uuid4())
        self.name = name
        self.task = task
        self.schedule = schedule


class ScheduledJob:
    def __init__(self, job, run_time):
        self.job = job
        self.run_time = run_time


# =========================
# TASK
# =========================
class Task(ABC):
    @abstractmethod
    def execute(self):
        pass


class PrintTask(Task):
    def execute(self):
        print(f"[{datetime.datetime.now()}] Executing PrintTask")


# =========================
# SCHEDULER ENGINE
# =========================
class SchedulerEngine:
    def __init__(self):
        self.jobs = {}  # job_id -> Job
        self.heap = []  # (run_time, job_id)
        self.lock = threading.Lock()
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.thread=threading.Thread(target=self.start, daemon=True)
        self.thread.start()

    def create_job(self, job_request: JobRequest):
        schedule = ScheduleFactory.get_instance(job_request.schedule_type)
        job = Job(job_request.name, job_request.task, schedule)

        run_time = schedule.next_run_time(datetime.datetime.now())

        with self.lock:
            self.jobs[job.id] = job
            heapq.heappush(self.heap, (run_time, job.id))

        return job.id

    def start(self):
        while self.running:
            with self.lock:
                if not self.heap:
                    wait = 1
                    job = None
                else:
                    run_time, job_id = self.heap[0]
                    now = datetime.datetime.now()
                    diff = (run_time - now).total_seconds()

                    if diff <= 0:
                        heapq.heappop(self.heap)
                        job = self.jobs.get(job_id)
                        wait = 0
                    else:
                        job = None
                        wait = min(diff, 1)

            # ---- outside lock ----
            if job:
                self.executor.submit(self.run_job, job)

            time.sleep(max(0, wait))

    def run_job(self, job):
        try:
            job.task.execute()
        finally:
            self.reschedule(job)

    def reschedule(self, job):
        next_time = job.schedule.next_run_time(datetime.datetime.now())

        with self.lock:
            if job.id in self.jobs:
                heapq.heappush(self.heap, (next_time, job.id))

    def cancel_job(self, job_id):
        with self.lock:
            if job_id in self.jobs:
                del self.jobs[job_id]  # lazy deletion

    def stop(self):
        self.running = False


# =========================
# MAIN
# =========================
def main():
    scheduler = SchedulerEngine()

    job1 = JobRequest("job1", PrintTask(), ScheduleType.HOURLY)
    scheduler.create_job(job1)

    time.sleep(5)
    scheduler.stop()


if __name__ == "__main__":
    main()