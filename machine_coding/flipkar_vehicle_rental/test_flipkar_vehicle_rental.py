import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from machine_coding.flipkar_vehicle_rental.flipkar_vehicle_rental import (
    BookingRejectedError,
    FlipKarRentalApp,
    ValidationError,
    seed_data,
)


class FlipKarVehicleRentalTest(unittest.TestCase):
    def setUp(self):
        self.app = FlipKarRentalApp()
        seed_data(self.app)
        self.start = datetime(2027, 2, 20, 10)
        self.end = datetime(2027, 2, 20, 12)
        self.now = datetime(2027, 2, 19, 10)

    def test_lowest_price_and_fallback(self):
        booking_1 = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )
        booking_2 = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )

        self.assertEqual("Malleshwaram", booking_1.branch_name)
        self.assertEqual("Koramangala", booking_2.branch_name)

    def test_no_vehicle_available(self):
        self.app.rental_service.rent_vehicle("suv", self.start, self.end, now=self.now)
        self.app.rental_service.rent_vehicle("suv", self.start, self.end, now=self.now)

        with self.assertRaises(BookingRejectedError):
            self.app.rental_service.rent_vehicle(
                "suv", self.start, self.end, now=self.now
            )

    def test_non_overlapping_slot_can_reuse_vehicle(self):
        booking_1 = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )
        booking_2 = self.app.rental_service.rent_vehicle(
            "suv",
            datetime(2027, 2, 20, 12),
            datetime(2027, 2, 20, 13),
            now=self.now,
        )

        self.assertEqual("Malleshwaram", booking_1.branch_name)
        self.assertEqual("Malleshwaram", booking_2.branch_name)

    def test_system_view(self):
        self.app.rental_service.rent_vehicle("suv", self.start, self.end, now=self.now)
        self.app.rental_service.rent_vehicle("suv", self.start, self.end, now=self.now)

        view = self.app.rental_service.system_view(
            datetime(2027, 2, 20, 11),
            datetime(2027, 2, 20, 12),
        )

        self.assertIn('All "suv" are booked.', view["Koramangala"])
        self.assertIn('All "suv" are booked.', view["Malleshwaram"])
        self.assertIn('"hatchback" is available for Rs.8', view["Jayanagar"])

    def test_booking_must_be_before_start_time(self):
        with self.assertRaises(ValidationError):
            self.app.rental_service.rent_vehicle(
                "bike",
                self.start,
                self.end,
                now=self.start,
            )

    def test_plural_vehicle_type_is_normalized(self):
        booking = self.app.rental_service.rent_vehicle(
            "bikes",
            self.start,
            self.end,
            now=self.now,
        )

        self.assertEqual("Malleshwaram", booking.branch_name)
        self.assertEqual("bike", booking.vehicle_type)

    def test_vehicle_type_index_tracks_matching_branches(self):
        branches = self.app.branch_repo.list_by_vehicle_type("suv")

        self.assertEqual(
            ["Koramangala", "Malleshwaram"],
            sorted(branch.name for branch in branches),
        )

    def test_booking_index_tracks_bookings_by_normalized_branch(self):
        booking = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )

        bookings = self.app.booking_repo.list_by_branch(" malleshwaram ")

        self.assertEqual([booking], bookings)

    def test_branch_name_comparison_is_normalized_for_availability(self):
        booking = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )
        booking.__dict__["branch_name"] = " malleshwaram "

        next_booking = self.app.rental_service.rent_vehicle(
            "suv", self.start, self.end, now=self.now
        )

        self.assertEqual("Malleshwaram", booking.branch_name.strip().title())
        self.assertEqual("Koramangala", next_booking.branch_name)

    def test_duration_must_be_full_hours(self):
        with self.assertRaises(ValidationError):
            self.app.rental_service.rent_vehicle(
                "bike",
                self.start,
                datetime(2027, 2, 20, 11, 30),
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
