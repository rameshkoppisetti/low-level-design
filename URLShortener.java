import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;

// ================= ENTITY =================
class Url {
    String longUrl;
    String shortCode;

    Url(String longUrl, String shortCode) {
        this.longUrl = longUrl;
        this.shortCode = shortCode;
    }
}

// ================= REPOSITORY =================
interface UrlRepository {
    void save(Url url);
    Url find(String shortCode);
}

class InMemoryUrlRepository implements UrlRepository {
    private final ConcurrentHashMap<String, Url> store = new ConcurrentHashMap<>();

    public void save(Url url) {
        store.put(url.shortCode, url);
    }

    public Url find(String shortCode) {
        return store.get(shortCode);
    }
}

// ================= KEY GENERATOR =================
class KeyGenerator {
    private static final String BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    private final AtomicLong counter = new AtomicLong(1);

    public String generate() {
        long id = counter.getAndIncrement();
        return encode(id);
    }

    private String encode(long num) {
        StringBuilder sb = new StringBuilder();
        while (num > 0) {
            sb.append(BASE62.charAt((int)(num % 62)));
            num /= 62;
        }
        return sb.reverse().toString();
    }
}

// ================= SERVICE =================
class UrlService {

    private final UrlRepository repo;
    private final KeyGenerator generator;

    UrlService(UrlRepository repo, KeyGenerator generator) {
        this.repo = repo;
        this.generator = generator;
    }

    public String shorten(String longUrl) {
        String code = generator.generate();

        Url url = new Url(longUrl, code);
        repo.save(url);

        return code;
    }

    public String resolve(String shortCode) {
        Url url = repo.find(shortCode);
        if (url == null) throw new RuntimeException("URL not found");
        return url.longUrl;
    }
}

// ================= MAIN =================
public class URLShortener {
    public static void main(String[] args) {

        UrlRepository repo = new InMemoryUrlRepository();
        KeyGenerator generator = new KeyGenerator();
        UrlService service = new UrlService(repo, generator);

        // shorten
        String code1 = service.shorten("https://google.com");
        String code2 = service.shorten("https://openai.com");

        System.out.println("Short URL 1: " + code1);
        System.out.println("Short URL 2: " + code2);

        // resolve
        System.out.println("Resolved: " + service.resolve(code1));
        System.out.println("Resolved: " + service.resolve(code2));
    }
}