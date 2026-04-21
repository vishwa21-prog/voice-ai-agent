"""
Appointment store.
Plain in-memory dict — obvious, easy to swap for a DB later.
"""

import uuid, logging
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

DOCTORS = {
    "dr_sharma": {"name": "Dr. Anjali Sharma", "speciality": "cardiologist",   "hospital": "Apollo"},
    "dr_patel":  {"name": "Dr. Rajan Patel",   "speciality": "dermatologist",  "hospital": "Fortis"},
    "dr_menon":  {"name": "Dr. Priya Menon",   "speciality": "neurologist",    "hospital": "MIOT"},
    "dr_iyer":   {"name": "Dr. Venkat Iyer",   "speciality": "general",        "hospital": "Apollo"},
}

DEFAULT_SLOTS = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]


def _resolve_date(s: str) -> str:
    s = (s or "tomorrow").lower().strip()
    today = date.today()
    if s == "today":    return today.strftime("%Y-%m-%d")
    if s == "tomorrow": return (today + timedelta(1)).strftime("%Y-%m-%d")
    # "next monday" etc.
    days = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
    for name, wd in days.items():
        if name in s:
            delta = (wd - today.weekday() + 7) % 7 or 7
            return (today + timedelta(delta)).strftime("%Y-%m-%d")
    return s  # assume already ISO


class AppointmentStore:
    def __init__(self):
        self._appts: dict[str, dict] = {}
        self._booked: dict[tuple, str] = {}  # (doctor_id, date, time) → appt_id

    def list_doctors(self) -> list[dict]:
        return [{"id": k, **v} for k, v in DOCTORS.items()]

    def check_slots(self, speciality=None, doctor_id=None, date_str=None) -> dict:
        if not doctor_id and speciality:
            matches = [k for k, v in DOCTORS.items() if speciality.lower() in v["speciality"]]
            if not matches:
                return {"available": False, "message": f"No {speciality} found"}
            doctor_id = matches[0]

        d = _resolve_date(date_str)
        taken = {t for (did, dd, t) in self._booked if did == doctor_id and dd == d}
        free = [s for s in DEFAULT_SLOTS if s not in taken]
        doc = DOCTORS.get(doctor_id, {})
        return {
            "doctor_id": doctor_id,
            "doctor_name": doc.get("name", doctor_id),
            "date": d,
            "free_slots": free,
            "available": bool(free),
        }

    def book(self, patient_id: str, doctor_id: str, date_str: str, time: str, reason="") -> dict:
        d = _resolve_date(date_str)
        key = (doctor_id, d, time)

        if key in self._booked:
            free = self.check_slots(doctor_id=doctor_id, date_str=d)["free_slots"]
            return {"success": False, "reason": "slot_taken", "alternatives": free[:3]}

        appt_dt = datetime.strptime(f"{d} {time}", "%Y-%m-%d %H:%M")
        if appt_dt < datetime.now():
            return {"success": False, "reason": "past_time"}

        appt_id = f"APT-{uuid.uuid4().hex[:6].upper()}"
        doc = DOCTORS.get(doctor_id, {})
        rec = {
            "id": appt_id, "patient_id": patient_id,
            "doctor_id": doctor_id, "doctor_name": doc.get("name", doctor_id),
            "speciality": doc.get("speciality", ""), "hospital": doc.get("hospital", ""),
            "date": d, "time": time, "reason": reason, "status": "confirmed",
        }
        self._appts[appt_id] = rec
        self._booked[key] = appt_id
        log.info(f"Booked {appt_id}: {doctor_id} {d} {time}")
        return {"success": True, "appointment": rec}

    def cancel(self, appt_id: str) -> dict:
        appt = self._appts.get(appt_id)
        if not appt:
            return {"success": False, "reason": "not_found"}
        key = (appt["doctor_id"], appt["date"], appt["time"])
        self._booked.pop(key, None)
        appt["status"] = "cancelled"
        return {"success": True}

    def reschedule(self, appt_id: str, new_date: str, new_time: str) -> dict:
        appt = self._appts.get(appt_id)
        if not appt:
            return {"success": False, "reason": "not_found"}
        nd = _resolve_date(new_date)
        new_key = (appt["doctor_id"], nd, new_time)
        if new_key in self._booked:
            free = self.check_slots(doctor_id=appt["doctor_id"], date_str=nd)["free_slots"]
            return {"success": False, "reason": "slot_taken", "alternatives": free[:3]}
        old_key = (appt["doctor_id"], appt["date"], appt["time"])
        self._booked.pop(old_key, None)
        appt["date"], appt["time"] = nd, new_time
        self._booked[new_key] = appt_id
        return {"success": True, "appointment": appt}

    def get_for_patient(self, patient_id: str) -> list[dict]:
        return [a for a in self._appts.values()
                if a["patient_id"] == patient_id and a["status"] != "cancelled"]
