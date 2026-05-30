import unittest

from machine_coding.flimble.flimble import (
    BoostPlan,
    CreateProfileRequest,
    FlimbleApp,
    Gender,
    PartnerPreferenceRequest,
    seed_data,
)


class FlimbleTest(unittest.TestCase):
    def setUp(self):
        self.app = FlimbleApp()
        self.ids = seed_data(self.app)

    def test_preferred_profile_ranked_by_mutual_interests(self):
        best = self.app.matching_service.get_best_profile(self.ids["aarav"])

        self.assertIsNotNone(best)
        self.assertEqual("Diya", best.name)

    def test_unpreferred_profile_only_shown_if_already_accepted_viewer(self):
        app = FlimbleApp()
        ps = app.profile_service
        ms = app.matching_service

        viewer = ps.create_profile(CreateProfileRequest("Viewer", 28, Gender.MALE))
        unpreferred = ps.create_profile(
            CreateProfileRequest("Older Candidate", 45, Gender.FEMALE)
        )

        ps.add_interests(viewer, ["books"])
        ps.add_interests(unpreferred, ["books"])
        ps.set_partner_preference(
            PartnerPreferenceRequest(viewer, 23, 30, Gender.FEMALE)
        )

        best_before_accept = ms.get_best_profile(viewer)
        self.assertIsNone(best_before_accept)

        ms.accept_profile(unpreferred, viewer)

        best_after_accept = ms.get_best_profile(viewer)
        self.assertEqual(unpreferred, best_after_accept.user_id)

    def test_mutual_accept_creates_match(self):
        ms = self.app.matching_service

        self.assertFalse(ms.accept_profile(self.ids["aarav"], self.ids["diya"]))
        self.assertTrue(ms.accept_profile(self.ids["diya"], self.ids["aarav"]))

        matches = ms.list_matched_profiles(self.ids["aarav"])
        self.assertEqual(["Diya"], [profile.name for profile in matches])

    def test_declined_profile_does_not_appear_again(self):
        ms = self.app.matching_service

        first = ms.get_best_profile(self.ids["rohan"])
        self.assertIsNotNone(first)

        ms.decline_profile(self.ids["rohan"], first.user_id)

        second = ms.get_best_profile(self.ids["rohan"])
        self.assertIsNotNone(second)
        self.assertNotEqual(first.user_id, second.user_id)

    def test_boost_prioritizes_candidate_inside_same_bucket(self):
        ps = self.app.profile_service
        ms = self.app.matching_service

        ps.buy_boost(self.ids["nisha"], BoostPlan.MEDIUM)

        best = ms.get_best_profile(self.ids["rohan"])
        self.assertEqual("Nisha", best.name)

    def test_duplicate_decision_is_rejected(self):
        ms = self.app.matching_service

        ms.accept_profile(self.ids["aarav"], self.ids["diya"])

        with self.assertRaises(ValueError):
            ms.decline_profile(self.ids["aarav"], self.ids["diya"])

    def test_admin_stats(self):
        ms = self.app.matching_service

        ms.accept_profile(self.ids["aarav"], self.ids["diya"])
        ms.accept_profile(self.ids["diya"], self.ids["aarav"])

        stats = self.app.admin_report_service.show_stats(top_n=2)

        self.assertEqual(6, stats["total_user_count"])
        self.assertEqual(2, stats["matched_users_count"])
        self.assertEqual({"MALE": 3, "FEMALE": 3}, stats["gender_cohort_size"])
        self.assertEqual(2, len(stats["top_users_with_highest_matches"]))


if __name__ == "__main__":
    unittest.main()
