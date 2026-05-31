# Practo Appointment Booking

## Requirements

- Register doctors with one speciality among:
  - Cardiologist
  - Dermatologist
  - Orthopedic
  - General Physician
- Register patients.
- Day is divided into 30-minute slots from 9 AM to 9 PM.
- Doctors declare availability for the current day.
- Patients search available slots by speciality.
- Default search ranking is by start time.
- Ranking strategy should be extensible.
- Patients can book available doctor slots.
- A patient can book multiple appointments in a day.
- A patient cannot book two appointments in the same time slot.
- Patients can cancel appointments.
- Canceled slots become available.
- Waitlist: if a patient tries to book a specific doctor slot that is already booked, add them to the waitlist.
- If the original booking is canceled, the first waitlisted patient gets the appointment.
- Patients and doctors can view booked appointments for the day.
- Bonus: show the trending doctor with the most active appointments.

