import java.util.concurrent.locks.ReentrantLock;

public class HashMapCustom {

    private Node[] buckets;
    private int capacity;
    private int size;
    private final double LOAD_FACTOR = 0.75;
    private final ReentrantLock lock = new ReentrantLock(); // ✅ reentrant lock

    public HashMapCustom(int capacity) {
        this.capacity = capacity;
        this.buckets = new Node[capacity];
        this.size = 0;
    }

    private int hash(int key) {
        return Integer.hashCode(key) % capacity;
    }

    public void put(int key, int value) {
        lock.lock();
        try {
            int index = hash(key);
            Node head = buckets[index];

            // check if key exists → update
            Node curr = head;
            while (curr != null) {
                if (curr.key == key) {
                    curr.value = value;
                    return;
                }
                curr = curr.next;
            }

            // insert at head
            Node newNode = new Node(key, value);
            newNode.next = head;
            buckets[index] = newNode;
            size++;

            // resize if needed
            if ((double) size / capacity > LOAD_FACTOR) {
                resize();
            }

        } finally {
            lock.unlock();
        }
    }

    public Integer get(int key) {
        lock.lock();
        try {
            int index = hash(key);
            Node curr = buckets[index];

            while (curr != null) {
                if (curr.key == key) {
                    return curr.value;
                }
                curr = curr.next;
            }
            return null;

        } finally {
            lock.unlock();
        }
    }

    private void resize() {
        Node[] oldBuckets = buckets;

        capacity *= 2;
        buckets = new Node[capacity];
        size = 0;

        // rehash
        for (Node head : oldBuckets) {
            Node curr = head;
            while (curr != null) {
                put(curr.key, curr.value); // safe due to ReentrantLock
                curr = curr.next;
            }
        }
    }

    // test

    public static void main(String[] args) throws InterruptedException {
    
            HashMapCustom map = new HashMapCustom(8);
    
            int threadCount = 10;
            int opsPerThread = 1000;
    
            Thread[] threads = new Thread[threadCount];
    
            // 🔹 Create threads
            for (int i = 0; i < threadCount; i++) {
                final int threadId = i;
    
                threads[i] = new Thread(() -> {
                    for (int j = 0; j < opsPerThread; j++) {
                        int key = threadId * opsPerThread + j;
                        map.put(key, key);
                    }
                });
            }
    
            // 🔹 Start all threads
            for (Thread t : threads) {
                t.start();
            }
    
            // 🔹 Wait for all threads to finish
            for (Thread t : threads) {
                t.join();
            }
    
            // 🔹 Validate results
            int success = 0;
            for (int i = 0; i < threadCount * opsPerThread; i++) {
                Integer val = map.get(i);
                if (val != null && val == i) {
                    success++;
                }
            }
    
            System.out.println("Expected: " + (threadCount * opsPerThread));
            System.out.println("Successful reads: " + success);
        }
}

class Node {
    int key;
    int value;
    Node next;

    Node(int key, int value) {
        this.key = key;
        this.value = value;
    }
}
