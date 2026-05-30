from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
import heapq
import uuid


class Gender(Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class Decision(Enum):
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class BoostPlan(Enum):
    SMALL = 3
    MEDIUM = 7
    LARGE = 15


class InterestCatalog:
    VALID_INTERESTS = {
        "pets",
        "football",
        "movies",
        "books",
        "music",
        "travel",
        "fitness",
        "food",
        "gaming",
        "photography",
    }

    @classmethod
    def validate(cls, interests: Set[str]) -> None:
        invalid = interests - cls.VALID_INTERESTS
        if invalid:
            raise ValueError(f"Invalid interests: {sorted(invalid)}")


@dataclass(frozen=True)
class PartnerPreference:
    min_age: int
    max_age: int
    gender: Optional[Gender] = None

    def matches(self, profile: "UserProfile") -> bool:
        if not (self.min_age <= profile.age <= self.max_age):
            return False
        if self.gender and profile.gender != self.gender:
            return False
        return True


@dataclass(frozen=True)
class PartnerPreferenceRequest:
    user_id: str
    min_age: int
    max_age: int
    gender: Optional[Gender] = None


@dataclass(frozen=True)
class CreateProfileRequest:
    name: str
    age: int
    gender: Gender


@dataclass
class UserProfile:
    user_id: str
    name: str
    age: int
    gender: Gender
    interests: Set[str] = field(default_factory=set)
    preference: Optional[PartnerPreference] = None
    boost_score: int = 0


@dataclass(frozen=True)
class ProfileRecommendation:
    profile: UserProfile
    bucket: int
    mutual_interests: int
    accepted_viewer: bool
    preferred: bool
    match_count: int
    boost_score: int


class UserRepository:
    def __init__(self):
        self.users: Dict[str, UserProfile] = {}
        self._lock = RLock()

    def save(self, user: UserProfile) -> None:
        with self._lock:
            self.users[user.user_id] = user

    def get(self, user_id: str) -> Optional[UserProfile]:
        with self._lock:
            return self.users.get(user_id)

    def list_all(self) -> List[UserProfile]:
        with self._lock:
            return list(self.users.values())

    def add_interests(self, user_id: str, interests: Set[str]) -> None:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise ValueError(f"User not found: {user_id}")
            user.interests.update(interests)

    def set_partner_preference(
        self,
        user_id: str,
        preference: PartnerPreference,
    ) -> None:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise ValueError(f"User not found: {user_id}")
            user.preference = preference

    def add_boost(self, user_id: str, boost_score: int) -> None:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise ValueError(f"User not found: {user_id}")
            user.boost_score += boost_score

    def consume_boost(self, user_id: str) -> None:
        with self._lock:
            user = self.users.get(user_id)
            if user and user.boost_score > 0:
                user.boost_score -= 1


class InteractionRepository:
    def __init__(self):
        self.decisions: Dict[Tuple[str, str], Decision] = {}
        self.matches: Set[Tuple[str, str]] = set()
        self.matches_by_user: Dict[str, Set[str]] = defaultdict(set)
        self._lock = RLock()

    def record_decision_once(
        self,
        from_user_id: str,
        to_user_id: str,
        decision: Decision,
    ) -> bool:
        with self._lock:
            key = (from_user_id, to_user_id)
            if key in self.decisions:
                raise ValueError("User has already acted on this profile")

            self.decisions[key] = decision

            if (
                decision == Decision.ACCEPTED
                and self.decisions.get((to_user_id, from_user_id)) == Decision.ACCEPTED
            ):
                match_key = self._match_key(from_user_id, to_user_id)
                if match_key not in self.matches:
                    self.matches.add(match_key)
                    self.matches_by_user[from_user_id].add(to_user_id)
                    self.matches_by_user[to_user_id].add(from_user_id)
                return True

            return False

    def has_decision(self, from_user_id: str, to_user_id: str) -> bool:
        with self._lock:
            return (from_user_id, to_user_id) in self.decisions

    def has_accepted(self, from_user_id: str, to_user_id: str) -> bool:
        with self._lock:
            return self.decisions.get((from_user_id, to_user_id)) == Decision.ACCEPTED

    def are_matched(self, user_a: str, user_b: str) -> bool:
        with self._lock:
            return self._match_key(user_a, user_b) in self.matches

    def list_matches(self, user_id: str) -> List[str]:
        with self._lock:
            return list(self.matches_by_user.get(user_id, set()))

    def match_count(self, user_id: str) -> int:
        with self._lock:
            return len(self.matches_by_user.get(user_id, set()))

    def match_counts_snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                user_id: len(matches)
                for user_id, matches in self.matches_by_user.items()
            }

    def _match_key(self, user_a: str, user_b: str) -> Tuple[str, str]:
        return tuple(sorted((user_a, user_b)))


class ProfileService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def create_profile(self, request: CreateProfileRequest) -> str:
        if request.age < 18:
            raise ValueError("User must be at least 18 years old")
        if not request.name.strip():
            raise ValueError("name cannot be empty")

        user_id = f"USR-{uuid.uuid4().hex[:8].upper()}"
        self.user_repo.save(
            UserProfile(
                user_id,
                request.name.strip(),
                request.age,
                request.gender,
            )
        )
        return user_id

    def add_interests(self, user_id: str, interests: List[str]) -> None:
        normalized = {interest.lower() for interest in interests}
        InterestCatalog.validate(normalized)
        self.user_repo.add_interests(user_id, normalized)

    def set_partner_preference(self, request: PartnerPreferenceRequest) -> None:
        if request.min_age > request.max_age:
            raise ValueError("min_age cannot be greater than max_age")
        preference = PartnerPreference(
            request.min_age,
            request.max_age,
            request.gender,
        )
        self.user_repo.set_partner_preference(request.user_id, preference)

    def buy_boost(self, user_id: str, plan: BoostPlan) -> None:
        self.user_repo.add_boost(user_id, plan.value)

    def _get_user_or_raise(self, user_id: str) -> UserProfile:
        user = self.user_repo.get(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")
        return user


class MatchingService:
    def __init__(self, user_repo: UserRepository, interaction_repo: InteractionRepository):
        self.user_repo = user_repo
        self.interaction_repo = interaction_repo

    def get_best_profile(self, user_id: str) -> Optional[UserProfile]:
        viewer = self._get_user_or_raise(user_id)
        recommendations = self._get_ranked_recommendations(viewer)

        if not recommendations:
            return None

        best = recommendations[0].profile

        self.user_repo.consume_boost(best.user_id)

        return best

    def accept_profile(self, from_user_id: str, to_user_id: str) -> bool:
        self._validate_interaction(from_user_id, to_user_id)
        return self.interaction_repo.record_decision_once(
            from_user_id,
            to_user_id,
            Decision.ACCEPTED,
        )

    def decline_profile(self, from_user_id: str, to_user_id: str) -> None:
        self._validate_interaction(from_user_id, to_user_id)
        self.interaction_repo.record_decision_once(
            from_user_id,
            to_user_id,
            Decision.DECLINED,
        )

    def list_matched_profiles(self, user_id: str) -> List[UserProfile]:
        self._get_user_or_raise(user_id)
        matched_ids = self.interaction_repo.list_matches(user_id)
        return [
            self.user_repo.get(matched_id)
            for matched_id in matched_ids
            if self.user_repo.get(matched_id)
        ]

    def _get_ranked_recommendations(
        self,
        viewer: UserProfile,
    ) -> List[ProfileRecommendation]:
        recommendations = []

        for candidate in self.user_repo.list_all():
            if candidate.user_id == viewer.user_id:
                continue
            if self.interaction_repo.has_decision(viewer.user_id, candidate.user_id):
                continue
            if self.interaction_repo.are_matched(viewer.user_id, candidate.user_id):
                continue

            accepted_viewer = self.interaction_repo.has_accepted(
                candidate.user_id,
                viewer.user_id,
            )
            preferred = self._is_preferred(viewer, candidate)

            if not preferred and not accepted_viewer:
                continue

            bucket = self._bucket(preferred, accepted_viewer)
            mutual_interests = len(viewer.interests & candidate.interests)
            match_count = self.interaction_repo.match_count(candidate.user_id)

            recommendations.append(
                ProfileRecommendation(
                    profile=candidate,
                    bucket=bucket,
                    mutual_interests=mutual_interests,
                    accepted_viewer=accepted_viewer,
                    preferred=preferred,
                    match_count=match_count,
                    boost_score=candidate.boost_score,
                )
            )

        return sorted(
            recommendations,
            key=lambda item: (
                item.bucket,
                -item.boost_score,
                item.match_count,
                -item.mutual_interests,
                item.profile.name,
            ),
        )

    def _is_preferred(self, viewer: UserProfile, candidate: UserProfile) -> bool:
        if not viewer.preference:
            return True
        return viewer.preference.matches(candidate)

    def _bucket(self, preferred: bool, accepted_viewer: bool) -> int:
        if preferred and accepted_viewer:
            return 0
        if preferred:
            return 1
        return 2

    def _validate_interaction(self, from_user_id: str, to_user_id: str) -> None:
        if from_user_id == to_user_id:
            raise ValueError("User cannot interact with own profile")
        self._get_user_or_raise(from_user_id)
        self._get_user_or_raise(to_user_id)

    def _get_user_or_raise(self, user_id: str) -> UserProfile:
        user = self.user_repo.get(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")
        return user


class AdminReportService:
    def __init__(self, user_repo: UserRepository, interaction_repo: InteractionRepository):
        self.user_repo = user_repo
        self.interaction_repo = interaction_repo

    def show_stats(self, top_n: int = 3) -> Dict[str, object]:
        users = self.user_repo.list_all()
        match_counts = self.interaction_repo.match_counts_snapshot()
        matched_user_ids = {
            user.user_id
            for user in users
            if match_counts.get(user.user_id, 0) > 0
        }

        top_users = heapq.nsmallest(
            top_n,
            users,
            key=lambda user: (
                -match_counts.get(user.user_id, 0),
                user.name,
            ),
        )

        return {
            "total_user_count": len(users),
            "matched_users_count": len(matched_user_ids),
            "top_users_with_highest_matches": [
                {
                    "user_id": user.user_id,
                    "name": user.name,
                    "matches": match_counts.get(user.user_id, 0),
                }
                for user in top_users
            ],
            "gender_cohort_size": self._gender_cohort(users),
            "age_cohort_size": self._age_cohort(users),
        }

    def _gender_cohort(self, users: List[UserProfile]) -> Dict[str, int]:
        cohort: Dict[str, int] = {}
        for user in users:
            cohort[user.gender.value] = cohort.get(user.gender.value, 0) + 1
        return cohort

    def _age_cohort(self, users: List[UserProfile]) -> Dict[str, int]:
        cohort = {"18-24": 0, "25-30": 0, "31-40": 0, "41+": 0}

        for user in users:
            if user.age <= 24:
                cohort["18-24"] += 1
            elif user.age <= 30:
                cohort["25-30"] += 1
            elif user.age <= 40:
                cohort["31-40"] += 1
            else:
                cohort["41+"] += 1

        return cohort


class FlimbleApp:
    def __init__(self):
        self.user_repo = UserRepository()
        self.interaction_repo = InteractionRepository()
        self.profile_service = ProfileService(self.user_repo)
        self.matching_service = MatchingService(self.user_repo, self.interaction_repo)
        self.admin_report_service = AdminReportService(
            self.user_repo,
            self.interaction_repo,
        )


def print_best(app: FlimbleApp, user_id: str, label: str) -> Optional[str]:
    profile = app.matching_service.get_best_profile(user_id)
    if profile:
        print(f"{label} best profile -> {profile.name}")
        return profile.user_id

    print(f"{label} best profile -> NONE")
    return None


def seed_data(app: FlimbleApp) -> Dict[str, str]:
    ps = app.profile_service

    ids = {
        "aarav": ps.create_profile(CreateProfileRequest("Aarav", 27, Gender.MALE)),
        "diya": ps.create_profile(CreateProfileRequest("Diya", 25, Gender.FEMALE)),
        "meera": ps.create_profile(CreateProfileRequest("Meera", 29, Gender.FEMALE)),
        "kabir": ps.create_profile(CreateProfileRequest("Kabir", 31, Gender.MALE)),
        "nisha": ps.create_profile(CreateProfileRequest("Nisha", 24, Gender.FEMALE)),
        "rohan": ps.create_profile(CreateProfileRequest("Rohan", 26, Gender.MALE)),
    }

    ps.add_interests(ids["aarav"], ["movies", "books", "fitness"])
    ps.add_interests(ids["diya"], ["movies", "books", "travel"])
    ps.add_interests(ids["meera"], ["music", "travel", "food"])
    ps.add_interests(ids["kabir"], ["football", "fitness", "movies"])
    ps.add_interests(ids["nisha"], ["books", "pets", "music"])
    ps.add_interests(ids["rohan"], ["gaming", "movies", "travel"])

    ps.set_partner_preference(PartnerPreferenceRequest(ids["aarav"], 23, 30, Gender.FEMALE))
    ps.set_partner_preference(PartnerPreferenceRequest(ids["diya"], 25, 32, Gender.MALE))
    ps.set_partner_preference(PartnerPreferenceRequest(ids["meera"], 25, 32, Gender.MALE))
    ps.set_partner_preference(PartnerPreferenceRequest(ids["kabir"], 23, 30, Gender.FEMALE))
    ps.set_partner_preference(PartnerPreferenceRequest(ids["nisha"], 24, 30, Gender.MALE))
    ps.set_partner_preference(PartnerPreferenceRequest(ids["rohan"], 23, 30, Gender.FEMALE))

    return ids


def main() -> None:
    app = FlimbleApp()
    ids = seed_data(app)

    print("=== Flimble Demo ===")

    best_for_aarav = print_best(app, ids["aarav"], "Aarav")
    if best_for_aarav:
        matched = app.matching_service.accept_profile(ids["aarav"], best_for_aarav)
        print(f"Aarav accepted -> matched: {matched}")

    matched = app.matching_service.accept_profile(ids["diya"], ids["aarav"])
    print(f"Diya accepted Aarav -> matched: {matched}")

    matches = app.matching_service.list_matched_profiles(ids["aarav"])
    print("Aarav matches:", [profile.name for profile in matches])

    app.profile_service.buy_boost(ids["nisha"], BoostPlan.MEDIUM)
    print("Nisha bought MEDIUM boost")

    best_for_rohan = print_best(app, ids["rohan"], "Rohan")
    if best_for_rohan:
        app.matching_service.decline_profile(ids["rohan"], best_for_rohan)
        print("Rohan declined shown profile")

    print_best(app, ids["rohan"], "Rohan")

    stats = app.admin_report_service.show_stats(top_n=3)
    print("Stats:", stats)


if __name__ == "__main__":
    main()
