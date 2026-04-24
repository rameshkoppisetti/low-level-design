import threading
import heapq
import datetime
import time
import queue


# ---------------- THREAD POOL ----------------
class ThreadPool:
    def __init__(self, num_workers):
        self.queue = queue.Queue()
        self.workers = []

        for _ in range(num_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)

    def submit(self, func, *args):
        self.queue.put((func, args))

    def _worker(self):
        while True:
            func, args = self.queue.get()
            try:
                func(*args)
            finally:
                self.queue.task_done()


# ---------------- TASK ----------------
class Task:
    def __init__(self, name, func, start_time, interval=None, executions=1):
        self.name = name
        self.func = func
        self.start_time = start_time
        self.interval = interval
        self.executions = executions

        # prevent overlap
        self.exec_lock = threading.Lock()

    def __lt__(self, other):
        return self.start_time < other.start_time


# ---------------- SCHEDULER ----------------
class TaskScheduler:
    def __init__(self, num_workers=4):
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.heap = []
        self.running = True

        self.thread_pool = ThreadPool(num_workers)

        self.scheduler_thread = threading.Thread(target=self._run, daemon=True)
        self.scheduler_thread.start()

    def schedule(self, task):
        with self.condition:
            heapq.heappush(self.heap, task)
            self.condition.notify()

    def _run(self):
        while self.running:
            with self.condition:
                while not self.heap:
                    self.condition.wait()

                task = self.heap[0]
                now = datetime.datetime.now()

                if task.start_time > now:
                    wait_time = (task.start_time - now).total_seconds()
                    self.condition.wait(timeout=wait_time)
                    continue

                heapq.heappop(self.heap)

            # -------- EXECUTION (via thread pool) --------
            if task.exec_lock.acquire(blocking=False):
                def run(t):
                    try:
                        t.func()
                    finally:
                        t.exec_lock.release()

                self.thread_pool.submit(run, task)

            # -------- RESCHEDULE --------
            if task.interval and task.executions > 1:
                task.executions -= 1
                task.start_time = datetime.datetime.now() + datetime.timedelta(seconds=task.interval)
                self.schedule(task)

    def stop(self):
        self.running = False
        with self.condition:
            self.condition.notify_all()


# ---------------- TEST ----------------
def work():
    print("Running at", datetime.datetime.now())
    time.sleep(2)


if __name__ == "__main__":
    scheduler = TaskScheduler(num_workers=3)

    # one-time task
    t1 = Task("task1", work, datetime.datetime.now() + datetime.timedelta(seconds=1))

    # recurring task
    t2 = Task(
        "task2",
        work,
        datetime.datetime.now() + datetime.timedelta(seconds=2),
        interval=3,
        executions=3
    )

    scheduler.schedule(t1)
    scheduler.schedule(t2)

    time.sleep(10)
    scheduler.stop()