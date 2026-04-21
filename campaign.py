"""
campaign.py — outbound reminder script
Run standalone: python campaign.py

Reads tomorrow's appointments and prints the call script for each patient.
In prod: swap the print() with a Twilio/Exotel API call.
"""

import json
from datetime import date, timedelta
from scheduler.appointments import AppointmentStore
from memory.store import MemoryStore

TEMPLATES = {
    "en": "Hi {name}, this is 2Care reminding you about your appointment with {doctor} tomorrow at {time}. Reply to reschedule.",
    "hi": "नमस्ते {name}, कल {time} बजे {doctor} के साथ आपका अपॉइंटमेंट है। बदलना हो तो बताएं।",
    "ta": "வணக்கம் {name}, நாளை {time} மணிக்கு {doctor} உடன் சந்திப்பு உள்ளது.",
}


def run_reminders():
    store = AppointmentStore()
    mem = MemoryStore()
    tomorrow = (date.today() + timedelta(1)).strftime("%Y-%m-%d")

    reminders_sent = 0
    for appt in store._appts.values():
        if appt["date"] != tomorrow or appt["status"] != "confirmed":
            continue

        patient_id = appt["patient_id"]
        profile = mem.get_profile(patient_id)
        lang = profile.get("lang", "en")
        name = profile.get("name", "Patient")
        template = TEMPLATES.get(lang, TEMPLATES["en"])
        message = template.format(name=name, doctor=appt["doctor_name"], time=appt["time"])

        print(f"📞 → {patient_id} | {lang} | {message}")
        # In production:
        # telephony.call(patient_id=patient_id, message=message, callback_ws="/ws/{patient_id}")
        reminders_sent += 1

    print(f"\nSent {reminders_sent} reminder(s)")


if __name__ == "__main__":
    run_reminders()
