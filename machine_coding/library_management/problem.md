# Library Management System

## Problem Definition

Design and implement a Library Management System that caters to registered members by cataloging and housing books that can be borrowed.

## Core Requirements

- Add books to the catalog.
- Every book is added by name and author.
- The system generates a unique book id by joining the first three letters of the author's last name with a number.
  - Example: a book by Rowling can have an id like `ROW1001`.
- The library can have more than one copy of a book.
- Register and unregister users in the library.
- A user should be able to request to borrow a book by book id.
- If a copy is available, the book should be reserved to the member.
- If all copies are borrowed, the requesting member should be added to a FIFO waitlist.
- When a book is returned:
  - Calculate fine if the user kept it for more than 14 days.
  - Fine is `20 rupees per delayed day`.
  - If a waitlist exists, the returned copy should immediately go to the first waitlisted user.

## Bonus / Good To Have

Do not code these for P0. Keep them for discussion.

- One user should only be allowed to reserve one copy of the same book.
- Auditing:
  - Given a book id, list users having that book.
  - Given a user id, list books issued to that user.

## Expectations

- In-memory data structures only.
- No UI, CLI, database, or REST API required.
- Code should be demo-able from a main driver.
- Keep the solution modular and readable.
- Handle edge cases gracefully.
