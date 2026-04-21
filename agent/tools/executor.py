"""
Tool Executor
Routes LLM tool calls to the appropriate AppointmentEngine methods.
"""

import logging
from typing import Any

from scheduler.appointment_engine import AppointmentEngine

logger = logging.getLogger("2care.tools")


class ToolExecutor:
    def __init__(self, appointment_engine: AppointmentEngine, patient_id: str):
        self.engine = appointment_engine
        self.patient_id = patient_id

        self._dispatch = {
            "checkAvailability": self._check_availability,
            "bookAppointment": self._book_appointment,
            "cancelAppointment": self._cancel_appointment,
            "rescheduleAppointment": self._reschedule_appointment,
            "getPatientAppointments": self._get_appointments,
            "listDoctors": self._list_doctors,
        }

    def execute(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        handler = self._dispatch.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return handler(tool_input)
        except Exception as e:
            logger.exception(f"Tool {tool_name} raised: {e}")
            return {"error": str(e)}

    def _check_availability(self, args: dict) -> dict:
        doctor_id = args.get("doctor_id")
        speciality = args.get("speciality")
        date = args.get("date", "tomorrow")

        if not doctor_id and speciality:
            doctors = self.engine.find_doctors_by_speciality(speciality)
            if not doctors:
                return {"available": False, "message": f"No {speciality} doctors found."}
            doctor_id = doctors[0]["id"]

        slots = self.engine.get_available_slots(doctor_id, date)
        return {
            "doctor_id": doctor_id,
            "date": date,
            "available_slots": slots,
            "available": len(slots) > 0,
        }

    def _book_appointment(self, args: dict) -> dict:
        patient_id = args.get("patient_id", self.patient_id)
        return self.engine.book_appointment(
            patient_id=patient_id,
            doctor_id=args["doctor_id"],
            date=args["date"],
            time_slot=args["time_slot"],
            reason=args.get("reason", ""),
        )

    def _cancel_appointment(self, args: dict) -> dict:
        return self.engine.cancel_appointment(args["appointment_id"])

    def _reschedule_appointment(self, args: dict) -> dict:
        return self.engine.reschedule_appointment(
            appointment_id=args["appointment_id"],
            new_date=args["new_date"],
            new_time_slot=args["new_time_slot"],
        )

    def _get_appointments(self, args: dict) -> dict:
        patient_id = args.get("patient_id", self.patient_id)
        status = args.get("status", "upcoming")
        appointments = self.engine.get_patient_appointments(patient_id, status)
        return {"appointments": appointments, "count": len(appointments)}

    def _list_doctors(self, args: dict) -> dict:
        speciality = args.get("speciality")
        if speciality:
            doctors = self.engine.find_doctors_by_speciality(speciality)
        else:
            doctors = self.engine.list_doctors()
        return {"doctors": doctors}
