import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.*;

// ---------------- TASK ----------------
class Task implements Comparable<Task> {
    String name;
    Runnable func;
    long runAt;          // epoch millis
    long interval;       // millis
    int executions;

    private final ReentrantLock execLock = new ReentrantLock();

    public Task(String name, Runnable func, long runAt, long interval, int executions) {
        this.name = name;
        this.func = func;
        this.runAt = runAt;
        this.interval = interval;
        this.executions = executions;
    }

    @Override
    public int compareTo(Task other) {
        return Long.compare(this.runAt, other.runAt);
    }

    public boolean tryLock() {
        return execLock.tryLock();
    }

    public void unlock() {
        execLock.unlock();
    }
}

// ---------------- SCHEDULER ----------------
class TaskScheduler {

    private final PriorityQueue<Task> heap = new PriorityQueue<>();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition condition = lock.newCondition();

    private final ExecutorService threadPool;
    private volatile boolean running = true;

    public TaskScheduler(int workers) {
        this.threadPool = Executors.newFixedThreadPool(workers);

        Thread schedulerThread = new Thread(this::run);
        schedulerThread.setDaemon(true);
        schedulerThread.start();
    }

    public void schedule(Task task) {
        lock.lock();
        try {
            heap.offer(task);
            condition.signal();
        } finally {
            lock.unlock();
        }
    }

    private void run() {
        while (running) {
            Task task;

            lock.lock();
            try {
                while (heap.isEmpty()) {
                    condition.await();
                }

                task = heap.peek();
                long now = System.currentTimeMillis();

                if (task.runAt > now) {
                    long waitTime = task.runAt - now;
                    condition.await(waitTime, TimeUnit.MILLISECONDS);
                    continue;
                }

                heap.poll();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                continue;
            } finally {
                lock.unlock();
            }

            // -------- EXECUTION --------
            if (task.tryLock()) {
                threadPool.submit(() -> {
                    try {
                        task.func.run();
                    } finally {
                        task.unlock();
                    }
                });
            }

            // -------- RESCHEDULE --------
            if (task.interval > 0 && task.executions > 1) {
                task.executions--;
                task.runAt = System.currentTimeMillis() + task.interval;
                schedule(task);
            }
        }
    }

    public void stop() {
        running = false;
        lock.lock();
        try {
            condition.signalAll();
        } finally {
            lock.unlock();
        }
        threadPool.shutdown();
    }
}

// ---------------- TEST ----------------
public class Main {
    public static void main(String[] args) throws InterruptedException {

        TaskScheduler scheduler = new TaskScheduler(3);

        Runnable work = () -> {
            System.out.println("Running at " + System.currentTimeMillis());
            try {
                Thread.sleep(2000);
            } catch (InterruptedException ignored) {}
        };

        // one-time task
        scheduler.schedule(new Task("task1", work,
                System.currentTimeMillis() + 1000, 0, 1));

        // recurring task
        scheduler.schedule(new Task("task2", work,
                System.currentTimeMillis() + 2000, 3000, 3));

        Thread.sleep(10000);
        scheduler.stop();
    }
}