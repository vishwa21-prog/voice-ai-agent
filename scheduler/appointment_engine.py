"""
Appointment Engine
Handles booking, cancellation, rescheduling, conflict detection,
and doctor availability. Uses an in-memory store (swap for PostgreSQL in prod).
"""

import uuid
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("2care.scheduler")

# Seed data ─────────────────────────────────────────────────────────────────────

DOCTORS = [
    {"id": "dr_sharma",  "name": "Dr. Anjali Sharma",  "speciality": "cardiologist",   "hospital": "Apollo"},
    {"id": "dr_patel",   "name": "Dr. Rajan Patel",    "speciality": "dermatologist",  "hospital": "Fortis"},
    {"id": "dr_menon",   "name": "Dr. Priya Menon",    "speciality": "neurologist",    "hospital": "MIOT"},
    {"id": "dr_kumar",   "name": "Dr. Suresh Kumar",   "speciality": "orthopedic",     "hospital": "Apollo"},
    {"id": "dr_rao",     "name": "Dr. Lakshmi Rao",    "speciality": "gynecologist",   "hospital": "Fortis"},
    {"id": "dr_iyer",    "name": "Dr. Venkat Iyer",    "speciality": "general",        "hospital": "MIOT"},
]

DEFAULT_SLOTS = ["09:00", "09:30", "10:00", "10:30", "11:00", "14:00", "14:30", "15:00", "16:00"]

# ────────────────────────────────────────────────────────────────────────────────


def _resolve_date(date_str: Optional[str]) -> str:
    """Convert relative date strings to YYYY-MM-DD."""
    if not date_str:
        return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    date_str = date_str.strip().lower()
    today = date.today()
    if date_str in ("today",):
        return today.strftime("%Y-%m-%d")
    if date_str in ("tomorrow",):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
    for name, weekday in days.items():
        if name in date_str:
            delta = (weekday - today.weekday() + 7) % 7 or 7
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")
    # Assume it's already ISO format
    return date_str


class AppointmentEngine:
    def __init__(self):
        # appointments[appointment_id] = {...}
        self._appointments: dict[str, dict] = {}
        # booked_slots[(doctor_id, date, time)] = appointment_id
        self._booked_slots: dict[tuple, str] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_doctors(self) -> list[dict]:
        return DOCTORS

    def find_doctors_by_speciality(self, speciality: str) -> list[dict]:
        spec = speciality.lower().strip()
        return [d for d in DOCTORS if spec in d["speciality"].lower()]

    def get_available_slots(self, doctor_id: Optional[str], date_str: Optional[str]) -> list[str]:
        resolved = _resolve_date(date_str)
        booked = {
            slot_time for (did, d, slot_time), _ in self._booked_slots.items()
            if did == doctor_id and d == resolved
        }
        available = [s for s in DEFAULT_SLOTS if s not in booked]
        logger.debug(f"Available slots for {doctor_id} on {resolved}: {available}")
        return available

    def book_appointment(
        self,
        patient_id: str,
        doctor_id: str,
        date_str: str,
        time_slot: str,
        reason: str = "",
    ) -> dict:
        resolved_date = _resolve_date(date_str)
        key = (doctor_id, resolved_date, time_slot)

        # Conflict detection
        if key in self._booked_slots:
            alternatives = self.get_available_slots(doctor_id, resolved_date)
            return {
                "success": False,
                "error": "slot_conflict",
                "message": f"Slot {time_slot} on {resolved_date} is already booked.",
                "alternatives": alternatives[:3],
            }

        # Past-time validation
        try:
            appt_dt = datetime.strptime(f"{resolved_date} {time_slot}", "%Y-%m-%d %H:%M")
            if appt_dt < datetime.now():
                return {"success": False, "error": "past_time", "message": "Cannot book an appointment in the past."}
        except ValueError:
            pass

        doctor = next((d for d in DOCTORS if d["id"] == doctor_id), None)
        appt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "id": appt_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "doctor_name": doctor["name"] if doctor else doctor_id,
            "speciality": doctor["speciality"] if doctor else "",
            "hospital": doctor["hospital"] if doctor else "",
            "date": resolved_date,
            "time": time_slot,
            "reason": reason,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }
        self._appointments[appt_id] = record
        self._booked_slots[key] = appt_id

        logger.info(f"✅ Booked {appt_id}: {doctor_id} on {resolved_date} at {time_slot}")
        return {"success": True, "appointment": record}

    def cancel_appointment(self, appointment_id: str) -> dict:
        appt = self._appointments.get(appointment_id)
        if not appt:
            return {"success": False, "error": "not_found", "message": f"Appointment {appointment_id} not found."}

        key = (appt["doctor_id"], appt["date"], appt["time"])
        self._booked_slots.pop(key, None)
        appt["status"] = "cancelled"
        logger.info(f"❌ Cancelled {appointment_id}")
        return {"success": True, "message": f"Appointment {appointment_id} cancelled."}

    def reschedule_appointment(self, appointment_id: str, new_date: str, new_time_slot: str) -> dict:
        appt = self._appointments.get(appointment_id)
        if not appt:
            return {"success": False, "error": "not_found", "message": f"Appointment {appointment_id} not found."}

        resolved_new_date = _resolve_date(new_date)
        new_key = (appt["doctor_id"], resolved_new_date, new_time_slot)

        if new_key in self._booked_slots:
            alternatives = self.get_available_slots(appt["doctor_id"], resolved_new_date)
            return {
                "success": False,
                "error": "slot_conflict",
                "message": f"Slot {new_time_slot} on {resolved_new_date} is already taken.",
                "alternatives": alternatives[:3],
            }

        # Free old slot
        old_key = (appt["doctor_id"], appt["date"], appt["time"])
        self._booked_slots.pop(old_key, None)

        # Book new slot
        appt["date"] = resolved_new_date
        appt["time"] = new_time_slot
        self._booked_slots[new_key] = appointment_id
        logger.info(f"🔄 Rescheduled {appointment_id} → {resolved_new_date} {new_time_slot}")
        return {"success": True, "appointment": appt}

    def get_patient_appointments(self, patient_id: str, status: str = "upcoming") -> list[dict]:
        now = datetime.now()
        results = []
        for appt in self._appointments.values():
            if appt["patient_id"] != patient_id:
                continue
            if appt["status"] == "cancelled":
                continue
            try:
                appt_dt = datetime.strptime(f"{appt['date']} {appt['time']}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if status == "upcoming" and appt_dt < now:
                continue
            if status == "past" and appt_dt >= now:
                continue
            results.append(appt)
        return sorted(results, key=lambda x: x["date"] + x["time"])
