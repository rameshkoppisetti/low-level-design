import java.util.*;
import java.util.concurrent.*;

// ================= EVENT =================
class Event {
    String id;
    String type;   // ORDER_PLACED, PAYMENT_SUCCESS
    String userId;
    String message;

    Event(String id, String type, String userId, String message) {
        this.id = id;
        this.type = type;
        this.userId = userId;
        this.message = message;
    }
}

// ================= SUBSCRIBER =================
interface Subscriber {
    void notify(Event event) throws Exception;
}

// ================= CHANNELS =================
class EmailSubscriber implements Subscriber {
    public void notify(Event event) {
        System.out.println("Email sent to " + event.userId + ": " + event.message);
    }
}

class SMSSubscriber implements Subscriber {
    public void notify(Event event) {
        System.out.println("SMS sent to " + event.userId + ": " + event.message);
    }
}

class PushSubscriber implements Subscriber {
    public void notify(Event event) {
        System.out.println("Push sent to " + event.userId + ": " + event.message);
    }
}

// ================= PUBLISHER =================
class EventPublisher {

    private final Map<String, List<Subscriber>> subscribers = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newFixedThreadPool(5);

    public void subscribe(String eventType, Subscriber sub) {
        subscribers.putIfAbsent(eventType, new ArrayList<>());
        subscribers.get(eventType).add(sub);
    }

    public void publish(Event event) {
        List<Subscriber> subs = subscribers.get(event.type);
        if (subs == null) return;

        for (Subscriber sub : subs) {
            executor.submit(() -> {
                try {
                    sub.notify(event);
                } catch (Exception e) {
                    RetryService.retry(event, sub);
                }
            });
        }
    }
}

// ================= RETRY =================
class RetryService {

    private static final int MAX_RETRIES = 3;

    public static void retry(Event event, Subscriber sub) {
        for (int i = 1; i <= MAX_RETRIES; i++) {
            try {
                Thread.sleep(1000 * i); // exponential backoff
                sub.notify(event);
                return;
            } catch (Exception ignored) {}
        }
        DeadLetterQueue.add(event);
    }
}

// ================= DLQ =================
class DeadLetterQueue {
    private static final List<Event> failedEvents = new ArrayList<>();

    public static void add(Event event) {
        failedEvents.add(event);
        System.out.println("Moved to DLQ: " + event.id);
    }
}

// ================= MAIN =================
public class NotificationSystem {
    public static void main(String[] args) {

        EventPublisher publisher = new EventPublisher();

        // subscribe channels
        publisher.subscribe("ORDER_PLACED", new EmailSubscriber());
        publisher.subscribe("ORDER_PLACED", new SMSSubscriber());
        publisher.subscribe("ORDER_PLACED", new PushSubscriber());

        // publish event
        Event event = new Event(
                UUID.randomUUID().toString(),
                "ORDER_PLACED",
                "user123",
                "Your order is placed successfully!"
        );

        publisher.publish(event);
    }
}