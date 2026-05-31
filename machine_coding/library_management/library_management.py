from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from threading import RLock
from typing import Deque, Dict, List, Optional


BORROW_DAYS = 14
FINE_PER_DAY = 20


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class BorrowRejectedError(Exception):
    pass


@dataclass(frozen=True)
class User:
    user_id: str
    name: str


@dataclass(frozen=True)
class BorrowRecord:
    user_id: str
    borrowed_on: date


@dataclass
class Book:
    book_id: str
    name: str
    author: str
    total_copies: int
    borrowed_by: Dict[str, BorrowRecord] = field(default_factory=dict)
    waitlist: Deque[str] = field(default_factory=deque)

    def available_copies(self) -> int:
        return self.total_copies - len(self.borrowed_by)

    def has_available_copy(self) -> bool:
        return self.available_copies() > 0


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def create(self, user: User) -> None:
        with self._lock:
            if user.user_id in self.users:
                raise ValidationError(f"User already exists: {user.user_id}")
            self.users[user.user_id] = user

    def get(self, user_id: str) -> User:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise NotFoundError(f"User not found: {user_id}")
            return user

    def delete(self, user_id: str) -> None:
        with self._lock:
            if user_id not in self.users:
                raise NotFoundError(f"User not found: {user_id}")
            del self.users[user_id]


class BookRepository:
    def __init__(self):
        self.books: Dict[str, Book] = {}
        self._lock = RLock()

    def create(self, book: Book) -> None:
        with self._lock:
            if book.book_id in self.books:
                raise ValidationError(f"Book already exists: {book.book_id}")
            self.books[book.book_id] = book

    def get(self, book_id: str) -> Book:
        with self._lock:
            book = self.books.get(book_id)
            if not book:
                raise NotFoundError(f"Book not found: {book_id}")
            return book

    def list_all(self) -> List[Book]:
        with self._lock:
            return list(self.books.values())


class LibraryService:
    def __init__(
        self,
        user_repo: UserRepository,
        book_repo: BookRepository,
    ):
        self.user_repo = user_repo
        self.book_repo = book_repo
        self._lock = RLock()
        self._next_number_by_prefix: Dict[str, int] = defaultdict(lambda: 1001)

    def add_book(self, name: str, author: str, copies: int = 1) -> str:
        if not name.strip() or not author.strip():
            raise ValidationError("Book name and author are required")
        if copies <= 0:
            raise ValidationError("Copies must be positive")

        with self._lock:
            book_id = self._next_book_id_locked(author)
            book = Book(
                book_id=book_id,
                name=name.strip(),
                author=author.strip(),
                total_copies=copies,
            )
            self.book_repo.create(book)
            return book_id

    def register_user(self, user_id: str, name: str) -> None:
        if not user_id.strip() or not name.strip():
            raise ValidationError("User id and name are required")
        self.user_repo.create(User(user_id.strip(), name.strip()))

    def unregister_user(self, user_id: str) -> None:
        self.user_repo.get(user_id)

        with self._lock:
            for book in self.book_repo.list_all():
                if user_id in book.borrowed_by:
                    raise ValidationError("Cannot unregister user with borrowed books")
                if user_id in book.waitlist:
                    raise ValidationError("Cannot unregister user in waitlist")
            self.user_repo.delete(user_id)

    def borrow_book(
        self,
        user_id: str,
        book_id: str,
        borrowed_on: Optional[date] = None,
    ) -> str:
        self.user_repo.get(user_id)
        borrowed_on = borrowed_on or date.today()

        with self._lock:
            book = self.book_repo.get(book_id)
            self._assign_available_copies_to_waitlist_locked(book, borrowed_on)

            if user_id in book.borrowed_by:
                raise BorrowRejectedError("User already borrowed this book")
            if user_id in book.waitlist:
                raise BorrowRejectedError("User already in waitlist")

            if book.has_available_copy() and not book.waitlist:
                book.borrowed_by[user_id] = BorrowRecord(user_id, borrowed_on)
                return "BORROWED"

            book.waitlist.append(user_id)
            return "WAITLISTED"

    def return_book(
        self,
        user_id: str,
        book_id: str,
        returned_on: Optional[date] = None,
    ) -> int:
        returned_on = returned_on or date.today()

        with self._lock:
            book = self.book_repo.get(book_id)
            borrow_record = book.borrowed_by.get(user_id)
            if not borrow_record:
                raise BorrowRejectedError("Book is not borrowed by this user")

            fine = self._calculate_fine(borrow_record.borrowed_on, returned_on)
            del book.borrowed_by[user_id]
            self._assign_to_next_waitlisted_user_locked(book, returned_on)
            return fine

    def book_status(self, book_id: str) -> Dict[str, object]:
        book = self.book_repo.get(book_id)
        return {
            "book_id": book.book_id,
            "name": book.name,
            "author": book.author,
            "total_copies": book.total_copies,
            "available_copies": book.available_copies(),
            "borrowed_by": sorted(book.borrowed_by),
            "waitlist": list(book.waitlist),
        }

    def _assign_to_next_waitlisted_user_locked(
        self,
        book: Book,
        borrowed_on: date,
    ) -> None:
        self._assign_available_copies_to_waitlist_locked(book, borrowed_on)

    def _assign_available_copies_to_waitlist_locked(
        self,
        book: Book,
        borrowed_on: date,
    ) -> None:
        while book.has_available_copy() and book.waitlist:
            next_user_id = book.waitlist.popleft()
            try:
                self.user_repo.get(next_user_id)
            except NotFoundError:
                continue
            if next_user_id in book.borrowed_by:
                continue
            book.borrowed_by[next_user_id] = BorrowRecord(next_user_id, borrowed_on)

    def _calculate_fine(self, borrowed_on: date, returned_on: date) -> int:
        borrowed_days = (returned_on - borrowed_on).days
        delayed_days = max(0, borrowed_days - BORROW_DAYS)
        return delayed_days * FINE_PER_DAY

    def _next_book_id_locked(self, author: str) -> str:
        prefix = self._author_prefix(author)
        number = self._next_number_by_prefix[prefix]
        self._next_number_by_prefix[prefix] += 1
        return f"{prefix}{number}"

    def _author_prefix(self, author: str) -> str:
        last_name = author.strip().split()[-1]
        return last_name[:3].upper().ljust(3, "X")


class LibraryApp:
    def __init__(self):
        self.user_repo = UserRepository()
        self.book_repo = BookRepository()
        self.library_service = LibraryService(self.user_repo, self.book_repo)


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_borrow_available_book() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Harry Potter", "J K Rowling", copies=1)
    service.register_user("u1", "User One")

    assert_equal("ROW1001", book_id, "book id generated from author last name")
    assert_equal("BORROWED", service.borrow_book("u1", book_id), "book borrowed")
    assert_equal(["u1"], service.book_status(book_id)["borrowed_by"], "borrower tracked")


def test_waitlist_and_promotion_on_return() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Clean Code", "Robert Martin", copies=1)
    service.register_user("u1", "User One")
    service.register_user("u2", "User Two")

    service.borrow_book("u1", book_id, date(2026, 1, 1))
    assert_equal("WAITLISTED", service.borrow_book("u2", book_id), "second user waitlisted")

    fine = service.return_book("u1", book_id, date(2026, 1, 10))

    assert_equal(0, fine, "no fine within 14 days")
    assert_equal(["u2"], service.book_status(book_id)["borrowed_by"], "waitlist promoted")
    assert_equal([], service.book_status(book_id)["waitlist"], "waitlist emptied")


def test_fine_after_due_date() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Design Patterns", "Erich Gamma", copies=1)
    service.register_user("u1", "User One")

    service.borrow_book("u1", book_id, date(2026, 1, 1))
    fine = service.return_book("u1", book_id, date(2026, 1, 20))

    assert_equal(100, fine, "fine is 20 per delayed day")


def test_multiple_copies() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Book", "Some Author", copies=2)
    service.register_user("u1", "User One")
    service.register_user("u2", "User Two")
    service.register_user("u3", "User Three")

    assert_equal("BORROWED", service.borrow_book("u1", book_id), "first copy borrowed")
    assert_equal("BORROWED", service.borrow_book("u2", book_id), "second copy borrowed")
    assert_equal("WAITLISTED", service.borrow_book("u3", book_id), "third user waitlisted")


def test_available_copy_serves_waitlist_first() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Book", "Some Author", copies=2)
    service.register_user("u1", "User One")
    service.register_user("u2", "User Two")
    service.register_user("u3", "User Three")

    book = service.book_repo.get(book_id)
    book.waitlist.append("u1")

    assert_equal("BORROWED", service.borrow_book("u2", book_id), "new borrower gets remaining copy")
    assert_equal(["u1", "u2"], service.book_status(book_id)["borrowed_by"], "waitlist served first")
    assert_equal([], service.book_status(book_id)["waitlist"], "waitlist drained")


def run_tests() -> None:
    test_borrow_available_book()
    test_waitlist_and_promotion_on_return()
    test_fine_after_due_date()
    test_multiple_copies()
    test_available_copy_serves_waitlist_first()


def main() -> None:
    app = LibraryApp()
    service = app.library_service

    book_id = service.add_book("Harry Potter", "J K Rowling", copies=1)
    service.register_user("u1", "User One")
    service.register_user("u2", "User Two")

    print(book_id)
    print(service.borrow_book("u1", book_id, date.today() - timedelta(days=16)))
    print(service.borrow_book("u2", book_id))
    print(service.book_status(book_id))
    print(service.return_book("u1", book_id))
    print(service.book_status(book_id))

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
