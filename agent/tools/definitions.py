"""
Tool definitions passed to the LLM for structured function calling.
"""

TOOL_DEFINITIONS = [
    {
        "name": "checkAvailability",
        "description": (
            "Check available appointment slots for a doctor on a given date. "
            "Always call this before booking to verify slot availability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {
                    "type": "string",
                    "description": "Unique doctor identifier (e.g. 'dr_sharma', 'dr_patel')",
                },
                "speciality": {
                    "type": "string",
                    "description": "Doctor speciality if doctor_id is unknown (e.g. 'cardiologist')",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format or relative like 'tomorrow', 'next Monday'",
                },
            },
            "required": [],
        },
    },
    {
        "name": "bookAppointment",
        "description": "Create a new appointment for the patient. Check availability first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "Doctor's unique ID"},
                "patient_id": {"type": "string", "description": "Patient's unique ID"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD"},
                "time_slot": {"type": "string", "description": "Time slot e.g. '10:30'"},
                "speciality": {"type": "string", "description": "Doctor speciality"},
                "reason": {"type": "string", "description": "Reason for visit (optional)"},
            },
            "required": ["doctor_id", "patient_id", "date", "time_slot"],
        },
    },
    {
        "name": "cancelAppointment",
        "description": "Cancel an existing appointment by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "Appointment ID to cancel"},
                "reason": {"type": "string", "description": "Reason for cancellation (optional)"},
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "rescheduleAppointment",
        "description": "Move an existing appointment to a new date/time slot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "Appointment ID to reschedule"},
                "new_date": {"type": "string", "description": "New date in YYYY-MM-DD"},
                "new_time_slot": {"type": "string", "description": "New time slot e.g. '14:00'"},
            },
            "required": ["appointment_id", "new_date", "new_time_slot"],
        },
    },
    {
        "name": "getPatientAppointments",
        "description": "Retrieve all upcoming and past appointments for the patient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["upcoming", "past", "all"],
                    "description": "Filter by status",
                },
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "listDoctors",
        "description": "List available doctors, optionally filtered by speciality.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speciality": {
                    "type": "string",
                    "description": "Filter by speciality e.g. 'cardiologist', 'dermatologist'",
                },
            },
            "required": [],
        },
    },
]
