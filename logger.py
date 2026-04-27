from enum import Enum
import datetime
from abc import ABC, abstractmethod
import threading
import queue


# ---------------- LOG LEVEL ----------------
class LogLevel(Enum):
    DEBUG = 1
    INFO = 2
    ERROR = 3


# ---------------- LOG MESSAGE ----------------
class LogMessage:
    def __init__(self, level, message):
        self.level = level
        self.message = message
        self.timestamp = datetime.datetime.now()
        self.thread_name = threading.current_thread().name


# ---------------- FORMATTER ----------------
class Formatter(ABC):
    @abstractmethod
    def format(self, log_message):
        pass


class SimpleFormatter(Formatter):
    def format(self, log_message):
        return f"{log_message.timestamp} [{log_message.level.name}] ({log_message.thread_name}) {log_message.message}"


# ---------------- APPENDER ----------------
class Appender(ABC):
    def __init__(self, formatter: Formatter):
        self.formatter = formatter

    @abstractmethod
    def append(self, log_message: LogMessage):
        pass


class ConsoleAppender(Appender):
    def __init__(self, formatter: Formatter):
        super().__init__(formatter)
        self.lock = threading.Lock()

    def append(self, log_message: LogMessage):
        with self.lock:
            print(self.formatter.format(log_message))

class FileAppender(Appender):
    def __init__(self, file_name, formatter: Formatter):
        super().__init__(formatter)
        self.file_name = file_name
        self.lock = threading.Lock()

        # keep file handle open (better performance)
        self.file = open(self.file_name, "a")

    def append(self, log: LogMessage):
        formatted = self.formatter.format(log)

        with self.lock:
            self.file.write(formatted + "\n")
            self.file.flush()   # ensure durability

    def close(self):
        with self.lock:
            self.file.close()

# ---------------- FILTER ----------------
class Filter(ABC):
    @abstractmethod
    def allow(self, log_message: LogMessage) -> bool:
        pass


class LevelFilter(Filter):
    def __init__(self, min_level: LogLevel):
        self.min_level = min_level

    def allow(self, log_message: LogMessage) -> bool:
        return log_message.level.value >= self.min_level.value


# ---------------- ASYNC APPENDER (Decorator) ----------------
class AsyncAppender(Appender):
    def __init__(self, appender: Appender, max_queue_size=0):
        # max_queue_size = 0 means unbounded
        self.appender = appender
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.running = True

        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def append(self, log_message: LogMessage):
        try:
            self.queue.put(log_message, block=False)
        except queue.Full:
            # drop log (can also block or log warning)
            pass

    def _worker(self):
        while self.running or not self.queue.empty():
            try:
                msg = self.queue.get(timeout=0.5)
                self.appender.append(msg)
                self.queue.task_done()
            except queue.Empty:
                continue

    def shutdown(self):
        self.running = False
        self.worker.join()


# ---------------- LOGGER ----------------
class Logger:
    def __init__(self):
        self.appenders = []
        self.filters = []

    def add_appender(self, appender: Appender):
        self.appenders.append(appender)

    def add_filter(self, filter_: Filter):
        self.filters.append(filter_)

    def log(self, level: LogLevel, message: str):
        log_message = LogMessage(level, message)

        # apply filters
        for f in self.filters:
            if not f.allow(log_message):
                return

        # fan-out to appenders
        for appender in self.appenders:
            appender.append(log_message)

    def debug(self, message):
        self.log(LogLevel.DEBUG, message)

    def info(self, message):
        self.log(LogLevel.INFO, message)

    def error(self, message):
        self.log(LogLevel.ERROR, message)


# ---------------- MAIN ----------------
def main():
    logger = Logger()

    formatter = SimpleFormatter()

    console_appender = ConsoleAppender(formatter)

    # wrap with async
    async_console = AsyncAppender(console_appender)

    logger.add_appender(async_console)

    # filter: only INFO and above
    logger.add_filter(LevelFilter(LogLevel.INFO))

    # logs
    logger.debug("This is debug (filtered)")
    logger.info("Application started")
    logger.error("Something failed")

    # allow async logs to flush
    import time
    time.sleep(1)


if __name__ == "__main__":
    main()