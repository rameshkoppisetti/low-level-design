import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from machine_coding.clearfit.clearfit import (
    AddWorkoutRequest,
    ClearFitApp,
    SessionRequest,
    SlotUnavailableError,
    ValidationError,
    seed_data,
)


class ClearFitTest(unittest.TestCase):
    def setUp(self):
        self.app = ClearFitApp()
        seed_data(self.app)

    def test_view_workout_availability_sorted_by_start_time(self):
        slots = self.app.availability_service.view_workout_availability("Weights")

        self.assertEqual(
            [("Koramangala", 6, 7), ("Bellandur", 20, 21), ("Bellandur", 21, 22)],
            [(slot.center_name, slot.start_time, slot.end_time) for slot in slots],
        )

    def test_view_workout_availability_by_center_sorted_by_available_seats(self):
        self.app.user_service.register("Vaibhav")
        self.app.booking_service.book_session(
            SessionRequest("Vaibhav", "Koramangala", "Weights", 6, 7)
        )

        slots = self.app.availability_service.view_workout_availability(
            "Weights",
            "Koramangala",
        )

        self.assertEqual(1, len(slots))
        self.assertEqual(99, slots[0].seats_available)

    def test_invalid_workout_timing_and_activity_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.workout_admin_service.add_workout(
                AddWorkoutRequest("Bellandur", "Weights", 18, 19, 100)
            )

        with self.assertRaises(ValidationError):
            self.app.workout_admin_service.add_workout(
                AddWorkoutRequest("Bellandur", "Swimming", 19, 20, 100)
            )

    def test_book_and_cancel_session(self):
        self.app.user_service.register("Vaibhav")

        booking = self.app.booking_service.book_session(
            SessionRequest("Vaibhav", "Koramangala", "Weights", 6, 7)
        )

        self.assertTrue(booking.booking_id.startswith("BKG-"))
        self.assertEqual(
            99,
            self.app.availability_service.view_workout_availability(
                "Weights",
                "Koramangala",
            )[0].seats_available,
        )

        self.app.booking_service.cancel_session(
            SessionRequest("Vaibhav", "Koramangala", "Weights", 6, 7)
        )

        self.assertEqual(
            100,
            self.app.availability_service.view_workout_availability(
                "Weights",
                "Koramangala",
            )[0].seats_available,
        )

    def test_concurrent_booking_does_not_oversell_slot(self):
        app = ClearFitApp()
        app.center_service.add_centre("HSR")
        app.center_service.add_centre_timings("HSR", [(6, 8)])
        app.center_service.add_centre_activities("HSR", ["Cardio"])
        app.workout_admin_service.add_workout(AddWorkoutRequest("HSR", "Cardio", 6, 7, 1))

        for user_name in ["U1", "U2", "U3", "U4"]:
            app.user_service.register(user_name)

        def try_book(user_name):
            try:
                app.booking_service.book_session(
                    SessionRequest(user_name, "HSR", "Cardio", 6, 7)
                )
                return True
            except SlotUnavailableError:
                return False

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(try_book, user_name)
                for user_name in ["U1", "U2", "U3", "U4"]
            ]

        results = [future.result() for future in as_completed(futures)]

        self.assertEqual(1, results.count(True))
        self.assertEqual(3, results.count(False))
        self.assertEqual(
            0,
            app.availability_service.view_workout_availability("Cardio", "HSR")[0]
            .seats_available,
        )


if __name__ == "__main__":
    unittest.main()
