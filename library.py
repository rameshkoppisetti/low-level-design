import uuid
from datetime import date
from collections import defaultdict


# =========================
# DOMAIN
# =========================

class Book:
    def __init__(self, id, title, author):
        self.id = id
        self.title = title
        self.author = author


class BookCopy:
    def __init__(self, id, book):
        self.id = id
        self.book = book
        self.available = True


class Member:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.loans = []


class Loan:
    def __init__(self, member, copy, due_date):
        self.id = str(uuid.uuid4())
        self.member = member
        self.copy = copy
        self.issue_date = date.today()
        self.due_date = due_date
        self.return_date = None


# =========================
# FINE STRATEGY
# =========================

class FineStrategy:
    def calculate(self, loan):
        raise NotImplementedError


class DefaultFineStrategy(FineStrategy):
    def calculate(self, loan):
        if not loan.return_date or loan.return_date <= loan.due_date:
            return 0

        days = (loan.return_date - loan.due_date).days
        return days * 10


class GracePeriodStrategy(FineStrategy):
    def calculate(self, loan):
        if not loan.return_date:
            return 0

        grace_days = 2
        delay = (loan.return_date - loan.due_date).days

        if delay <= grace_days:
            return 0

        return (delay - grace_days) * 10


# =========================
# SEARCH SERVICE
# =========================

class SearchService:
    def __init__(self):
        self.title_index = defaultdict(list)
        self.author_index = defaultdict(list)

    def index(self, book):
        self.title_index[book.title.lower()].append(book)
        self.author_index[book.author.lower()].append(book)

    def search_by_title(self, title):
        return self.title_index.get(title.lower(), [])

    def search_by_author(self, author):
        return self.author_index.get(author.lower(), [])


# =========================
# LIBRARY SERVICE
# =========================

class LibraryService:
    def __init__(self, fine_strategy=None):
        self.books = {}
        self.inventory = defaultdict(list)      # book_id → copies
        self.available_count = defaultdict(int)
        self.loans = {}
        self.search = SearchService()
        self.fine_strategy = fine_strategy or DefaultFineStrategy()

    # ---------- ADD BOOK ----------
    def add_book(self, book, num_copies):
        self.books[book.id] = book
        self.search.index(book)

        for _ in range(num_copies):
            copy = BookCopy(str(uuid.uuid4()), book)
            self.inventory[book.id].append(copy)
            self.available_count[book.id] += 1

    # ---------- SEARCH ----------
    def search_title(self, title):
        return self.search.search_by_title(title)

    def search_author(self, author):
        return self.search.search_by_author(author)

    # ---------- ISSUE ----------
    def issue(self, member, book_id, due_date):
        if self.available_count[book_id] == 0:
            print("❌ No copies available")
            return None

        for copy in self.inventory[book_id]:
            if copy.available:
                copy.available = False
                self.available_count[book_id] -= 1

                loan = Loan(member, copy, due_date)
                self.loans[loan.id] = loan
                member.loans.append(loan)

                print(f"✅ Book issued: {copy.book.title}")
                return loan

    # ---------- RETURN ----------
    def return_book(self, loan_id):
        loan = self.loans.get(loan_id)

        if not loan:
            print("Invalid loan")
            return

        loan.return_date = date.today()
        loan.copy.available = True
        self.available_count[loan.copy.book.id] += 1

        loan.member.loans.remove(loan)

        # 🔥 Fine via strategy
        fine = self.fine_strategy.calculate(loan)

        print(f"📚 Returned: {loan.copy.book.title}")
        print(f"💰 Fine: ₹{fine}")

        return fine


# =========================
# DEMO
# =========================

def main():
    service = LibraryService()

    book1 = Book("b1", "Clean Code", "Robert Martin")
    book2 = Book("b2", "System Design", "Alex Xu")

    service.add_book(book1, 2)
    service.add_book(book2, 1)

    member = Member("m1", "Satya")

    # 🔍 Search
    print("Search by title:", [b.title for b in service.search_title("Clean Code")])

    # 📚 Issue
    loan = service.issue(member, "b1", date(2026, 4, 25))

    # 📥 Return (simulate late return)
    if loan:
        loan.return_date = date(2026, 4, 30)  # simulate delay
        service.return_book(loan.id)


if __name__ == "__main__":
    main()