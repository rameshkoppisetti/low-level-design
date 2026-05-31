# Bug Bounty Management System

## Problem Definition

Flipkart wants to build an in-house platform to manage its Bug Bounty Program.
External reporters send bug reports by email, and Flipkart employees manually register those reports in this system.

## Terminologies

- `User`: Flipkart employee using the system.
- `Reporter`: External user who reported the bug through email.
- `BugReport`: The bug bounty report registered in the system.

## Must Have Requirements

- User entity with basic profile: name, email, role.
- Users can be hardcoded/preloaded initially.
- Ability to login/logout.
- Logged-in user can create a bug report.
- Required bug report fields:
  - title
  - description
  - status
  - severity
  - bounty amount
  - reporter email
  - assigned user
  - created timestamp
  - closed timestamp
- Supported statuses:
  - Open
  - ReportReview
  - Rejected
  - Acknowledged
  - BountyReview
  - BountyPaid
  - Closed
- A user can assign bug reports to any user.
- A user can change the status of reports assigned to them.
- A user can edit a bug report.
- A user can add internal comments.
- Admin users can delete reports.
- Non-admin users cannot delete reports.
- A user can view:
  - all bug reports
  - reports assigned to them
  - reports assigned to them and completed
  - reports assigned to them and incomplete

## Bonus Capabilities

These can be discussed or added later:

- Add new users dynamically.
- Update existing users.
- Send communication to the reporter.
- Preserve status update timelines.
- Log time spent on a bug report.
- Enforce status transitions:
  - Open -> ReportReview
  - ReportReview -> Rejected or Acknowledged
  - Rejected -> Closed
  - Acknowledged -> BountyReview
  - BountyReview -> BountyPaid
  - BountyPaid -> Closed

## Expectations

- Working and demonstrable code.
- Functionally correct.
- Thread-safe where shared state is mutated.
- Modular and readable.
- Separation of concerns.
- Extensible with minimal changes.
- Easy to test.
- Proper error handling.
