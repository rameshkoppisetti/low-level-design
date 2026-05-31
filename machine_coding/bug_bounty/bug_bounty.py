from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Dict, List, Optional


class Role(Enum):
    ADMIN = "admin"
    AGENT = "agent"


class BugStatus(Enum):
    OPEN = "Open"
    REPORT_REVIEW = "ReportReview"
    REJECTED = "Rejected"
    ACKNOWLEDGED = "Acknowledged"
    BOUNTY_REVIEW = "BountyReview"
    BOUNTY_PAID = "BountyPaid"
    CLOSED = "Closed"


class Severity(Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class AuthorizationError(Exception):
    pass


class InvalidStateError(Exception):
    pass


@dataclass(frozen=True)
class User:
    username: str
    name: str
    email: str
    role: Role


@dataclass(frozen=True)
class Comment:
    comment_id: str
    user_name: str
    text: str
    created_at: datetime


@dataclass
class BugReport:
    report_id: str
    title: str
    description: str
    severity: Severity
    reporter_email: str
    created_by: str
    status: BugStatus = BugStatus.OPEN
    bounty_amount: int = 0
    assigned_user: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    comments: List[Comment] = field(default_factory=list)

    def is_completed(self) -> bool:
        return self.status in (BugStatus.CLOSED, BugStatus.REJECTED)


class UserRepository:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self._lock = RLock()

    def preload(self, users: List[User]) -> None:
        with self._lock:
            for user in users:
                if user.username in self.users:
                    raise ValidationError(f"User already exists: {user.username}")
                self.users[user.username] = user

    def get(self, username: str) -> User:
        with self._lock:
            user = self.users.get(username)
            if not user:
                raise NotFoundError(f"User not found: {username}")
            return user


class BugReportRepository:
    def __init__(self):
        self.reports: Dict[str, BugReport] = {}
        self.report_ids_by_title: Dict[str, str] = {}
        self.reports_by_assignee: Dict[str, set[str]] = {}
        self._lock = RLock()

    def create(self, report: BugReport) -> None:
        with self._lock:
            title_key = self._title_key(report.title)
            if title_key in self.report_ids_by_title:
                raise ValidationError(f"Bug report already exists: {report.title}")

            self.reports[report.report_id] = report
            self.report_ids_by_title[title_key] = report.report_id
            if report.assigned_user:
                self._add_assignee_index(report.assigned_user, report.report_id)

    def get_by_title(self, title: str) -> BugReport:
        with self._lock:
            report_id = self.report_ids_by_title.get(self._title_key(title))
            if not report_id:
                raise NotFoundError(f"Bug report not found: {title}")
            return self.reports[report_id]

    def list_all(self) -> List[BugReport]:
        with self._lock:
            return list(self.reports.values())

    def list_by_assignee(self, username: str) -> List[BugReport]:
        with self._lock:
            return [
                self.reports[report_id]
                for report_id in self.reports_by_assignee.get(username, set())
                if report_id in self.reports
            ]

    def update_assignee(self, report: BugReport, new_assignee: str) -> None:
        with self._lock:
            if report.assigned_user:
                self.reports_by_assignee.get(report.assigned_user, set()).discard(
                    report.report_id
                )
            report.assigned_user = new_assignee
            self._add_assignee_index(new_assignee, report.report_id)

    def delete(self, report: BugReport) -> None:
        with self._lock:
            del self.reports[report.report_id]
            del self.report_ids_by_title[self._title_key(report.title)]
            if report.assigned_user:
                self.reports_by_assignee.get(report.assigned_user, set()).discard(
                    report.report_id
                )

    def _add_assignee_index(self, username: str, report_id: str) -> None:
        self.reports_by_assignee.setdefault(username, set()).add(report_id)

    def _title_key(self, title: str) -> str:
        return title.strip().lower()


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
        self.current_user: Optional[User] = None
        self._lock = RLock()

    def login(self, username: str) -> None:
        user = self.user_repo.get(username)
        with self._lock:
            self.current_user = user

    def logout(self) -> None:
        with self._lock:
            self.current_user = None

    def require_user(self) -> User:
        with self._lock:
            if not self.current_user:
                raise AuthorizationError("User must be logged in")
            return self.current_user


class BugBountyService:
    def __init__(
        self,
        user_repo: UserRepository,
        report_repo: BugReportRepository,
        auth_service: AuthService,
    ):
        self.user_repo = user_repo
        self.report_repo = report_repo
        self.auth_service = auth_service
        self._lock = RLock()
        self._next_report_number = 1
        self._next_comment_number = 1

    def preload_users(self, users: List[User]) -> None:
        self.user_repo.preload(users)

    def report_bug(
        self,
        title: str,
        description: str,
        severity: Severity,
        reporter_email: str,
    ) -> BugReport:
        user = self.auth_service.require_user()
        self._validate_report_input(title, description, reporter_email)

        with self._lock:
            report = BugReport(
                report_id=self._next_report_id_locked(),
                title=title.strip(),
                description=description.strip(),
                severity=severity,
                reporter_email=reporter_email.strip(),
                created_by=user.username,
            )
            self.report_repo.create(report)
            return report

    def assign_bug_report(self, title: str, assignee: str) -> None:
        self.auth_service.require_user()
        self.user_repo.get(assignee)

        with self._lock:
            report = self.report_repo.get_by_title(title)
            self.report_repo.update_assignee(report, assignee)

    def update_bug_status(self, title: str, status: BugStatus) -> None:
        user = self.auth_service.require_user()

        with self._lock:
            report = self.report_repo.get_by_title(title)
            self._require_assigned_user(report, user)
            self._validate_status_transition(report.status, status)

            report.status = status
            if status == BugStatus.CLOSED:
                report.closed_at = datetime.now()

    def update_bug_report(
        self,
        title: str,
        description: Optional[str] = None,
        severity: Optional[Severity] = None,
        bounty_amount: Optional[int] = None,
        reporter_email: Optional[str] = None,
    ) -> None:
        user = self.auth_service.require_user()

        with self._lock:
            report = self.report_repo.get_by_title(title)
            self._require_assigned_user(report, user)

            if description is not None:
                if not description.strip():
                    raise ValidationError("Description cannot be empty")
                report.description = description.strip()
            if severity is not None:
                report.severity = severity
            if bounty_amount is not None:
                if bounty_amount < 0:
                    raise ValidationError("Bounty amount cannot be negative")
                report.bounty_amount = bounty_amount
            if reporter_email is not None:
                if not reporter_email.strip():
                    raise ValidationError("Reporter email cannot be empty")
                report.reporter_email = reporter_email.strip()

    def add_comment(self, title: str, text: str) -> None:
        user = self.auth_service.require_user()
        if not text.strip():
            raise ValidationError("Comment cannot be empty")

        with self._lock:
            report = self.report_repo.get_by_title(title)
            report.comments.append(
                Comment(
                    comment_id=self._next_comment_id_locked(),
                    user_name=user.username,
                    text=text.strip(),
                    created_at=datetime.now(),
                )
            )

    def delete_bug_report(self, title: str) -> None:
        user = self.auth_service.require_user()
        if user.role != Role.ADMIN:
            raise AuthorizationError("Only admin can delete bug reports")

        with self._lock:
            report = self.report_repo.get_by_title(title)
            self.report_repo.delete(report)

    def list_all_bug_reports(self) -> List[BugReport]:
        self.auth_service.require_user()
        return sorted(self.report_repo.list_all(), key=lambda report: report.created_at)

    def list_assigned_reports(self) -> List[BugReport]:
        user = self.auth_service.require_user()
        return sorted(
            self.report_repo.list_by_assignee(user.username),
            key=lambda report: report.created_at,
        )

    def list_assigned_completed_reports(self) -> List[BugReport]:
        return [
            report
            for report in self.list_assigned_reports()
            if report.is_completed()
        ]

    def list_assigned_incomplete_reports(self) -> List[BugReport]:
        return [
            report
            for report in self.list_assigned_reports()
            if not report.is_completed()
        ]

    def view_bug_report_details(self, title: str) -> BugReport:
        self.auth_service.require_user()
        return self.report_repo.get_by_title(title)

    def _require_assigned_user(self, report: BugReport, user: User) -> None:
        if report.assigned_user != user.username:
            raise AuthorizationError("Only assigned user can update this report")

    def _validate_status_transition(
        self,
        current_status: BugStatus,
        next_status: BugStatus,
    ) -> None:
        allowed = {
            BugStatus.OPEN: {BugStatus.REPORT_REVIEW},
            BugStatus.REPORT_REVIEW: {BugStatus.REJECTED, BugStatus.ACKNOWLEDGED},
            BugStatus.REJECTED: {BugStatus.CLOSED},
            BugStatus.ACKNOWLEDGED: {BugStatus.BOUNTY_REVIEW},
            BugStatus.BOUNTY_REVIEW: {BugStatus.BOUNTY_PAID},
            BugStatus.BOUNTY_PAID: {BugStatus.CLOSED},
            BugStatus.CLOSED: set(),
        }
        if next_status not in allowed[current_status]:
            raise InvalidStateError(
                f"Invalid transition: {current_status.value} -> {next_status.value}"
            )

    def _validate_report_input(
        self,
        title: str,
        description: str,
        reporter_email: str,
    ) -> None:
        if not title.strip():
            raise ValidationError("Title is required")
        if not description.strip():
            raise ValidationError("Description is required")
        if not reporter_email.strip():
            raise ValidationError("Reporter email is required")

    def _next_report_id_locked(self) -> str:
        report_id = f"BUG-{self._next_report_number}"
        self._next_report_number += 1
        return report_id

    def _next_comment_id_locked(self) -> str:
        comment_id = f"C-{self._next_comment_number}"
        self._next_comment_number += 1
        return comment_id


class BugBountyApp:
    def __init__(self):
        self.user_repo = UserRepository()
        self.report_repo = BugReportRepository()
        self.auth_service = AuthService(self.user_repo)
        self.bug_bounty_service = BugBountyService(
            self.user_repo,
            self.report_repo,
            self.auth_service,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def preload_users(service: BugBountyService) -> None:
    service.preload_users(
        [
            User("user1", "User One", "user1@flipkart.com", Role.ADMIN),
            User("user2", "User Two", "user2@flipkart.com", Role.AGENT),
        ]
    )


def test_report_assignment_and_status_flow() -> None:
    app = BugBountyApp()
    service = app.bug_bounty_service
    preload_users(service)

    app.auth_service.login("user1")
    service.report_bug("Bug Title 1", "Bug Description 1", Severity.P0, "r1@email.com")
    service.assign_bug_report("Bug Title 1", "user1")
    service.update_bug_status("Bug Title 1", BugStatus.REPORT_REVIEW)
    service.update_bug_status("Bug Title 1", BugStatus.ACKNOWLEDGED)
    service.update_bug_status("Bug Title 1", BugStatus.BOUNTY_REVIEW)
    service.update_bug_report("Bug Title 1", bounty_amount=1000)
    service.add_comment("Bug Title 1", "comment text 1")

    report = service.view_bug_report_details("Bug Title 1")
    assert_equal(BugStatus.BOUNTY_REVIEW, report.status, "status updated")
    assert_equal(1000, report.bounty_amount, "bounty updated")
    assert_equal(1, len(report.comments), "comment added")


def test_only_assigned_user_can_update() -> None:
    app = BugBountyApp()
    service = app.bug_bounty_service
    preload_users(service)

    app.auth_service.login("user1")
    service.report_bug("Bug Title 2", "Bug Description 2", Severity.P1, "r2@email.com")
    service.assign_bug_report("Bug Title 2", "user2")

    rejected = False
    try:
        service.update_bug_status("Bug Title 2", BugStatus.REPORT_REVIEW)
    except AuthorizationError:
        rejected = True

    assert_equal(True, rejected, "non-assigned user cannot update")


def test_admin_delete_only() -> None:
    app = BugBountyApp()
    service = app.bug_bounty_service
    preload_users(service)

    app.auth_service.login("user1")
    service.report_bug("Bug Title 3", "Bug Description 3", Severity.P2, "r3@email.com")
    service.assign_bug_report("Bug Title 3", "user2")
    app.auth_service.logout()

    app.auth_service.login("user2")
    rejected = False
    try:
        service.delete_bug_report("Bug Title 3")
    except AuthorizationError:
        rejected = True
    assert_equal(True, rejected, "agent cannot delete")

    app.auth_service.logout()
    app.auth_service.login("user1")
    service.delete_bug_report("Bug Title 3")
    assert_equal(0, len(service.list_all_bug_reports()), "admin deleted report")


def test_assigned_report_filters() -> None:
    app = BugBountyApp()
    service = app.bug_bounty_service
    preload_users(service)

    app.auth_service.login("user1")
    service.report_bug("Bug Title 4", "Bug Description 4", Severity.P0, "r4@email.com")
    service.report_bug("Bug Title 5", "Bug Description 5", Severity.P0, "r5@email.com")
    service.assign_bug_report("Bug Title 4", "user2")
    service.assign_bug_report("Bug Title 5", "user2")
    app.auth_service.logout()

    app.auth_service.login("user2")
    service.update_bug_status("Bug Title 4", BugStatus.REPORT_REVIEW)
    service.update_bug_status("Bug Title 4", BugStatus.REJECTED)
    service.update_bug_status("Bug Title 4", BugStatus.CLOSED)

    assert_equal(2, len(service.list_assigned_reports()), "assigned reports")
    assert_equal(1, len(service.list_assigned_completed_reports()), "completed reports")
    assert_equal(1, len(service.list_assigned_incomplete_reports()), "incomplete reports")


def run_tests() -> None:
    test_report_assignment_and_status_flow()
    test_only_assigned_user_can_update()
    test_admin_delete_only()
    test_assigned_report_filters()


def main() -> None:
    app = BugBountyApp()
    service = app.bug_bounty_service
    preload_users(service)

    app.auth_service.login("user1")
    service.report_bug(
        "Bug Title 1",
        "Bug Description 1",
        Severity.P0,
        "reporter.b1@email.com",
    )
    service.report_bug(
        "Bug Title 2",
        "Bug Description 2",
        Severity.P0,
        "reporter.b2@email.com",
    )
    service.assign_bug_report("Bug Title 1", "user1")
    service.assign_bug_report("Bug Title 2", "user2")
    service.update_bug_status("Bug Title 1", BugStatus.REPORT_REVIEW)
    service.update_bug_status("Bug Title 1", BugStatus.ACKNOWLEDGED)
    service.update_bug_status("Bug Title 1", BugStatus.BOUNTY_REVIEW)
    service.update_bug_report("Bug Title 1", bounty_amount=1000)
    service.add_comment("Bug Title 1", "comment text 1")

    print([report.title for report in service.list_all_bug_reports()])
    print(service.view_bug_report_details("Bug Title 1"))
    app.auth_service.logout()

    app.auth_service.login("user2")
    service.update_bug_status("Bug Title 2", BugStatus.REPORT_REVIEW)
    service.update_bug_status("Bug Title 2", BugStatus.REJECTED)
    service.update_bug_status("Bug Title 2", BugStatus.CLOSED)
    print([report.title for report in service.list_assigned_completed_reports()])

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
