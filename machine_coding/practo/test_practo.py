import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from machine_coding.practo.practo import (
    PractoApp,
    SlotUnavailableError,
    Speciality,
    ValidationError,
)


class PractoTest(unittest.TestCase):
    def test_search_slots_ranked_by_start_time(self):
        app = PractoApp()
        service = app.practo_service
        service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
        service.declare_availability("d1", ["10am-10.30am", "9am-9.30am", "9.30am-10am"])

        slots = service.search_slots(Speciality.CARDIOLOGIST)

        self.assertEqual(["09:00", "09:30", "10:00"], [slot.slot for slot in slots])

    def test_booked_slot_waitlist_promotes_on_cancel(self):
        app = PractoApp()
        service = app.practo_service
        service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
        service.register_patient("p1", "Patient A")
        service.register_patient("p2", "Patient B")
        service.declare_availability("d1", ["9am-9.30am"])

        appointment = service.book_appointment("p1", "d1", "9am-9.30am")

        with self.assertRaises(SlotUnavailableError):
            service.book_appointment("p2", "d1", "9am-9.30am")

        service.cancel_appointment(appointment.appointment_id)

        self.assertEqual(
            ["p2"],
            [item.patient_id for item in service.view_doctor_appointments("d1")],
        )

    def test_patient_cannot_double_book_same_slot(self):
        app = PractoApp()
        service = app.practo_service
        service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
        service.register_doctor("d2", "Dr B", Speciality.DERMATOLOGIST)
        service.register_patient("p1", "Patient A")
        service.declare_availability("d1", ["10am-10.30am"])
        service.declare_availability("d2", ["10am-10.30am"])

        service.book_appointment("p1", "d1", "10am-10.30am")

        with self.assertRaises(ValidationError):
            service.book_appointment("p1", "d2", "10am-10.30am")

    def test_am_pm_slot_input_is_normalized(self):
        app = PractoApp()
        service = app.practo_service
        service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
        service.declare_availability(
            "d1",
            ["9.30am-10am", "10am-10.30am", "9am-9.30am"],
        )

        slots = service.search_slots(Speciality.CARDIOLOGIST)

        self.assertEqual(["09:00", "09:30", "10:00"], [slot.slot for slot in slots])

    def test_invalid_slot_rejected(self):
        app = PractoApp()
        service = app.practo_service
        service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)

        with self.assertRaises(ValidationError):
            service.declare_availability("d1", ["9pm-9.30pm"])


if __name__ == "__main__":
    unittest.main()
