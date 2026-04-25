import uuid
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict


# =========================
# ENUMS
# =========================

class SeatStatus:
    AVAILABLE = "AVAILABLE"
    LOCKED = "LOCKED"
    BOOKED = "BOOKED"


class BookingStatus:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# =========================
# DOMAIN
# =========================

class Movie:
    def __init__(self, id, title, duration_mins):
        self.id = id
        self.title = title
        self.duration = duration_mins


class Seat:
    def __init__(self, seat_id):
        self.id = seat_id


class Screen:
    def __init__(self, id, name, seats):
        self.id = id
        self.name = name
        self.seats = seats  # static layout


class Theatre:
    def __init__(self, id, name, city):
        self.id = id
        self.name = name
        self.city = city
        self.screens = []

    def add_screen(self, screen):
        self.screens.append(screen)


class Show:
    def __init__(self, movie, screen, start_time: datetime):
        self.id = str(uuid.uuid4())
        self.movie = movie
        self.screen = screen
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=movie.duration)

        # per-show seat state
        self.seat_status = {s.id: SeatStatus.AVAILABLE for s in screen.seats}
        self.locks = {s.id: threading.Lock() for s in screen.seats}


class Booking:
    def __init__(self, user_id, show_id, seats):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.show_id = show_id
        self.seats = seats
        self.status = BookingStatus.PENDING


# =========================
# SHOW SERVICE
# =========================

class ShowService:
    def __init__(self):
        self.shows_by_screen = defaultdict(list)

    def add_show(self, show: Show):
        screen_id = show.screen.id

        # prevent overlap
        for existing in self.shows_by_screen[screen_id]:
            if self._overlap(existing, show):
                raise Exception("Show timing conflict!")

        self.shows_by_screen[screen_id].append(show)

    def _overlap(self, s1, s2):
        return not (s2.end_time <= s1.start_time or s2.start_time >= s1.end_time)


# =========================
# SEARCH SERVICE
# =========================

class SearchService:
    def __init__(self):
        self.movie_index = defaultdict(list)
        self.city_index = defaultdict(list)

    def index_show(self, show, theatre):
        self.movie_index[show.movie.id].append(show)
        self.city_index[theatre.city.lower()].append(show)

    def search(self, movie_id=None, city=None):
        shows = self.movie_index.get(movie_id, [])

        if city:
            city_shows = set(self.city_index.get(city.lower(), []))
            shows = [s for s in shows if s in city_shows]

        return shows


# =========================
# SEAT AVAILABILITY SERVICE
# =========================

class SeatAvailabilityService:
    def __init__(self, show):
        self.show = show

    def get_available(self):
        return [s for s, st in self.show.seat_status.items() if st == SeatStatus.AVAILABLE]

    def lock(self, seat_ids):
        acquired = []

        for sid in seat_ids:
            lock = self.show.locks[sid]

            if not lock.acquire(blocking=False):
                self.release(acquired)
                return False

            if self.show.seat_status[sid] != SeatStatus.AVAILABLE:
                self.release(acquired)
                return False

            self.show.seat_status[sid] = SeatStatus.LOCKED
            acquired.append(sid)

        return True

    def confirm(self, seat_ids):
        for sid in seat_ids:
            self.show.seat_status[sid] = SeatStatus.BOOKED
            self.show.locks[sid].release()

    def release(self, seat_ids):
        for sid in seat_ids:
            self.show.seat_status[sid] = SeatStatus.AVAILABLE
            self.show.locks[sid].release()

    def _rollback(self, seats):
        for s in seats:
            self.show.locks[s].release()


# =========================
# PAYMENT SERVICE
# =========================

class PaymentService:
    def process(self, user_id, amount):
        # mock payment success
        return True


# =========================
# BOOKING SERVICE
# =========================

class BookingService:
    def __init__(self, payment_service):
        self.bookings = {}
        self.payment = payment_service

    def book(self, user_id, show, seat_ids):
        seat_service = SeatAvailabilityService(show)

        # STEP 1: LOCK
        if not seat_service.lock(seat_ids):
            print("❌ Seats unavailable")
            return None

        booking = Booking(user_id, show.id, seat_ids)

        # STEP 2: PAYMENT
        success = self.payment.process(user_id, amount=100)

        if success:
            seat_service.confirm(seat_ids)
            booking.status = BookingStatus.CONFIRMED
            print(f"✅ Booking confirmed: {seat_ids}")
        else:
            seat_service.release(seat_ids)
            booking.status = BookingStatus.CANCELLED

        self.bookings[booking.id] = booking
        return booking

    def cancel(self, booking, show):
        seat_service = SeatAvailabilityService(show)

        seat_service.release(booking.seats)
        booking.status = BookingStatus.CANCELLED
        print("❌ Booking cancelled")


# =========================
# DEMO
# =========================

def main():
    # Movie
    movie = Movie("m1", "Inception", 150)

    # Theatre + Screen
    theatre = Theatre("t1", "PVR", "Bangalore")
    seats = [Seat(f"S{i}") for i in range(1, 6)]
    screen = Screen("screen1", "Screen 1", seats)
    theatre.add_screen(screen)

    # Show
    show_service = ShowService()
    show = Show(movie, screen, datetime(2026, 4, 20, 10, 0))
    show_service.add_show(show)

    # Search
    search = SearchService()
    search.index_show(show, theatre)

    results = search.search(movie_id="m1", city="Bangalore")
    print("Shows:", [s.id for s in results])

    # Booking
    booking_service = BookingService(PaymentService())

    booking1 = booking_service.book("user1", show, ["S1", "S2"])
    booking2 = booking_service.book("user2", show, ["S2", "S3"])  # conflict

    # Cancel
    if booking1:
        booking_service.cancel(booking1, show)


if __name__ == "__main__":
    main()