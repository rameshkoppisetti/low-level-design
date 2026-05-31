from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Deque, Dict, List, Optional, Set


class Speciality(Enum):
    CARDIOLOGIST = "Cardiologist"
    DERMATOLOGIST = "Dermatologist"
    ORTHOPEDIC = "Orthopedic"
    GENERAL_PHYSICIAN = "General Physician"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class SlotUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class Doctor:
    doctor_id: str
    name: str
    speciality: Speciality


@dataclass(frozen=True)
class Patient:
    patient_id: str
    name: str


@dataclass
class DoctorSlot:
    doctor_id: str
    slot: str
    appointment_id: Optional[str] = None
    waitlist: Deque[str] = field(default_factory=deque)

    def is_available(self) -> bool:
        return self.appointment_id is None


@dataclass(frozen=True)
class Appointment:
    appointment_id: str
    doctor_id: str
    patient_id: str
    slot: str


@dataclass(frozen=True)
class SlotOption:
    doctor_id: str
    doctor_name: str
    speciality: Speciality
    slot: str


class DoctorRepository:
    def __init__(self):
        self.doctors: Dict[str, Doctor] = {}
        self.doctors_by_speciality: Dict[Speciality, Set[str]] = defaultdict(set)
        self._lock = RLock()

    def create(self, doctor: Doctor) -> None:
        with self._lock:
            if doctor.doctor_id in self.doctors:
                raise ValidationError(f"Doctor already exists: {doctor.doctor_id}")
            self.doctors[doctor.doctor_id] = doctor
            self.doctors_by_speciality[doctor.speciality].add(doctor.doctor_id)

    def get(self, doctor_id: str) -> Doctor:
        with self._lock:
            doctor = self.doctors.get(doctor_id)
            if not doctor:
                raise NotFoundError(f"Doctor not found: {doctor_id}")
            return doctor

    def list_by_speciality(self, speciality: Speciality) -> List[Doctor]:
        with self._lock:
            return [
                self.doctors[doctor_id]
                for doctor_id in self.doctors_by_speciality.get(speciality, set())
            ]


class PatientRepository:
    def __init__(self):
        self.patients: Dict[str, Patient] = {}
        self._lock = RLock()

    def create(self, patient: Patient) -> None:
        with self._lock:
            if patient.patient_id in self.patients:
                raise ValidationError(f"Patient already exists: {patient.patient_id}")
            self.patients[patient.patient_id] = patient

    def get(self, patient_id: str) -> Patient:
        with self._lock:
            patient = self.patients.get(patient_id)
            if not patient:
                raise NotFoundError(f"Patient not found: {patient_id}")
            return patient


class SlotRepository:
    def __init__(self):
        self.slots_by_doctor: Dict[str, Dict[str, DoctorSlot]] = defaultdict(dict)
        self._lock = RLock()

    def create(self, doctor_id: str, slot: str) -> None:
        with self._lock:
            if slot not in self.slots_by_doctor[doctor_id]:
                self.slots_by_doctor[doctor_id][slot] = DoctorSlot(doctor_id, slot)

    def get(self, doctor_id: str, slot: str) -> DoctorSlot:
        with self._lock:
            doctor_slot = self.slots_by_doctor.get(doctor_id, {}).get(slot)
            if not doctor_slot:
                raise NotFoundError(f"Slot not found for doctor={doctor_id}, slot={slot}")
            return doctor_slot

    def list_by_doctor(self, doctor_id: str) -> List[DoctorSlot]:
        with self._lock:
            return list(self.slots_by_doctor.get(doctor_id, {}).values())


class AppointmentRepository:
    def __init__(self):
        self.appointments: Dict[str, Appointment] = {}
        self.appointments_by_patient: Dict[str, Set[str]] = defaultdict(set)
        self.appointments_by_doctor: Dict[str, Set[str]] = defaultdict(set)
        self._lock = RLock()

    def create(self, appointment: Appointment) -> None:
        with self._lock:
            self.appointments[appointment.appointment_id] = appointment
            self.appointments_by_patient[appointment.patient_id].add(
                appointment.appointment_id
            )
            self.appointments_by_doctor[appointment.doctor_id].add(
                appointment.appointment_id
            )

    def get(self, appointment_id: str) -> Appointment:
        with self._lock:
            appointment = self.appointments.get(appointment_id)
            if not appointment:
                raise NotFoundError(f"Appointment not found: {appointment_id}")
            return appointment

    def delete(self, appointment_id: str) -> Appointment:
        with self._lock:
            appointment = self.get(appointment_id)
            del self.appointments[appointment_id]
            self.appointments_by_patient[appointment.patient_id].discard(appointment_id)
            self.appointments_by_doctor[appointment.doctor_id].discard(appointment_id)
            return appointment

    def list_by_patient(self, patient_id: str) -> List[Appointment]:
        with self._lock:
            return [
                self.appointments[appointment_id]
                for appointment_id in self.appointments_by_patient.get(patient_id, set())
            ]

    def list_by_doctor(self, doctor_id: str) -> List[Appointment]:
        with self._lock:
            return [
                self.appointments[appointment_id]
                for appointment_id in self.appointments_by_doctor.get(doctor_id, set())
            ]


class StartTimeRankingStrategy:
    def rank(self, slots: List[SlotOption]) -> List[SlotOption]:
        return sorted(
            slots,
            key=lambda slot: (_slot_start_minutes(slot.slot), slot.doctor_id),
        )


class PractoService:
    def __init__(
        self,
        doctor_repo: DoctorRepository,
        patient_repo: PatientRepository,
        slot_repo: SlotRepository,
        appointment_repo: AppointmentRepository,
    ):
        self.doctor_repo = doctor_repo
        self.patient_repo = patient_repo
        self.slot_repo = slot_repo
        self.appointment_repo = appointment_repo
        self.ranking_strategy = StartTimeRankingStrategy()
        self._lock = RLock()
        self._next_appointment_number = 1

    def register_doctor(
        self,
        doctor_id: str,
        name: str,
        speciality: Speciality,
    ) -> None:
        if not doctor_id.strip() or not name.strip():
            raise ValidationError("Doctor id and name are required")
        self.doctor_repo.create(
            Doctor(doctor_id.strip(), name.strip(), speciality)
        )

    def register_patient(self, patient_id: str, name: str) -> None:
        if not patient_id.strip() or not name.strip():
            raise ValidationError("Patient id and name are required")
        self.patient_repo.create(Patient(patient_id.strip(), name.strip()))

    def declare_availability(self, doctor_id: str, slots: List[str]) -> None:
        self.doctor_repo.get(doctor_id)
        if not slots:
            raise ValidationError("At least one slot is required")

        for slot in slots:
            self.slot_repo.create(doctor_id, _normalize_slot(slot))

    def search_slots(self, speciality: Speciality) -> List[SlotOption]:
        options = []
        for doctor in self.doctor_repo.list_by_speciality(speciality):
            for doctor_slot in self.slot_repo.list_by_doctor(doctor.doctor_id):
                if doctor_slot.is_available():
                    options.append(
                        SlotOption(
                            doctor_id=doctor.doctor_id,
                            doctor_name=doctor.name,
                            speciality=doctor.speciality,
                            slot=doctor_slot.slot,
                        )
                    )
        return self.ranking_strategy.rank(options)

    def book_appointment(
        self,
        patient_id: str,
        doctor_id: str,
        slot: str,
    ) -> Appointment:
        self.patient_repo.get(patient_id)
        self.doctor_repo.get(doctor_id)
        slot = _normalize_slot(slot)

        with self._lock:
            doctor_slot = self.slot_repo.get(doctor_id, slot)

            if self._patient_has_conflict(patient_id, slot):
                raise ValidationError("Patient already has appointment in this slot")

            if not doctor_slot.is_available():
                if patient_id not in doctor_slot.waitlist:
                    doctor_slot.waitlist.append(patient_id)
                raise SlotUnavailableError("Slot already booked; patient waitlisted")

            appointment = self._create_appointment_locked(patient_id, doctor_id, slot)
            doctor_slot.appointment_id = appointment.appointment_id
            return appointment

    def cancel_appointment(self, appointment_id: str) -> None:
        with self._lock:
            appointment = self.appointment_repo.delete(appointment_id)
            doctor_slot = self.slot_repo.get(appointment.doctor_id, appointment.slot)
            doctor_slot.appointment_id = None
            self._promote_waitlisted_patient_locked(doctor_slot)

    def view_patient_appointments(self, patient_id: str) -> List[Appointment]:
        self.patient_repo.get(patient_id)
        return sorted(
            self.appointment_repo.list_by_patient(patient_id),
            key=lambda appointment: _slot_start_minutes(appointment.slot),
        )

    def view_doctor_appointments(self, doctor_id: str) -> List[Appointment]:
        self.doctor_repo.get(doctor_id)
        return sorted(
            self.appointment_repo.list_by_doctor(doctor_id),
            key=lambda appointment: _slot_start_minutes(appointment.slot),
        )

    def _promote_waitlisted_patient_locked(self, doctor_slot: DoctorSlot) -> None:
        while doctor_slot.waitlist:
            patient_id = doctor_slot.waitlist.popleft()
            if self._patient_has_conflict(patient_id, doctor_slot.slot):
                continue

            appointment = self._create_appointment_locked(
                patient_id,
                doctor_slot.doctor_id,
                doctor_slot.slot,
            )
            doctor_slot.appointment_id = appointment.appointment_id
            return

    def _create_appointment_locked(
        self,
        patient_id: str,
        doctor_id: str,
        slot: str,
    ) -> Appointment:
        appointment = Appointment(
            appointment_id=self._next_appointment_id_locked(),
            doctor_id=doctor_id,
            patient_id=patient_id,
            slot=slot,
        )
        self.appointment_repo.create(appointment)
        return appointment

    def _patient_has_conflict(self, patient_id: str, slot: str) -> bool:
        for appointment in self.appointment_repo.list_by_patient(patient_id):
            if appointment.slot == slot:
                return True
        return False

    def _next_appointment_id_locked(self) -> str:
        appointment_id = f"Appointment Id#{self._next_appointment_number}"
        self._next_appointment_number += 1
        return appointment_id


class PractoApp:
    def __init__(self):
        self.doctor_repo = DoctorRepository()
        self.patient_repo = PatientRepository()
        self.slot_repo = SlotRepository()
        self.appointment_repo = AppointmentRepository()
        self.practo_service = PractoService(
            self.doctor_repo,
            self.patient_repo,
            self.slot_repo,
            self.appointment_repo,
        )


def build_valid_slots() -> Set[str]:
    slots = set()
    current = 9 * 60
    end = 21 * 60

    while current < end:
        slots.add(_minutes_to_time(current))
        current += 30

    return slots


def _normalize_slot(slot: str) -> str:
    original_slot = slot
    slot = slot.strip().lower().replace(" ", "")

    if "-" not in slot:
        raise ValidationError(f"Invalid slot: {original_slot}")

    start = slot.split("-", 1)[0]
    if not (start.endswith("am") or start.endswith("pm")):
        raise ValidationError(f"Invalid slot: {original_slot}")

    suffix = start[-2:]
    time_part = start[:-2]

    try:
        if "." in time_part:
            hour_text, minute_text = time_part.split(".")
        else:
            hour_text, minute_text = time_part, "00"

        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        raise ValidationError(f"Invalid slot: {original_slot}")

    if suffix == "pm" and hour != 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0

    normalized = f"{hour:02d}:{minute:02d}"
    if normalized not in VALID_SLOTS:
        raise ValidationError(f"Invalid slot: {original_slot}")
    return normalized


def _minutes_to_time(minutes: int) -> str:
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _slot_start_minutes(slot: str) -> int:
    hour_text, minute_text = slot.split(":")
    return int(hour_text) * 60 + int(minute_text)


VALID_SLOTS = build_valid_slots()


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def test_search_booking_and_cancel_waitlist() -> None:
    app = PractoApp()
    service = app.practo_service

    service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
    service.register_patient("p1", "Patient A")
    service.register_patient("p2", "Patient B")
    service.declare_availability("d1", ["9am-9.30am", "9.30am-10am"])

    slots = service.search_slots(Speciality.CARDIOLOGIST)
    assert_equal(["09:00", "09:30"], [slot.slot for slot in slots], "rank by start time")

    appointment = service.book_appointment("p1", "d1", "9am-9.30am")

    waitlisted = False
    try:
        service.book_appointment("p2", "d1", "9am-9.30am")
    except SlotUnavailableError:
        waitlisted = True
    assert_equal(True, waitlisted, "booked slot adds waitlist")

    service.cancel_appointment(appointment.appointment_id)
    assert_equal(
        ["p2"],
        [item.patient_id for item in service.view_doctor_appointments("d1")],
        "waitlisted patient promoted",
    )


def test_patient_slot_conflict() -> None:
    app = PractoApp()
    service = app.practo_service

    service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
    service.register_doctor("d2", "Dr B", Speciality.DERMATOLOGIST)
    service.register_patient("p1", "Patient A")
    service.declare_availability("d1", ["10am-10.30am"])
    service.declare_availability("d2", ["10am-10.30am"])

    service.book_appointment("p1", "d1", "10am-10.30am")

    rejected = False
    try:
        service.book_appointment("p1", "d2", "10am-10.30am")
    except ValidationError:
        rejected = True
    assert_equal(True, rejected, "patient cannot double book slot")


def run_tests() -> None:
    test_search_booking_and_cancel_waitlist()
    test_patient_slot_conflict()


def main() -> None:
    app = PractoApp()
    service = app.practo_service

    service.register_doctor("d1", "Dr A", Speciality.CARDIOLOGIST)
    service.register_patient("p1", "Patient A")
    service.declare_availability("d1", ["9am-9.30am", "9.30am-10am"])
    print(service.search_slots(Speciality.CARDIOLOGIST))
    print(service.book_appointment("p1", "d1", "9am-9.30am"))

    print("Tests:")
    run_tests()


if __name__ == "__main__":
    main()
