"""
Campaign Scheduler
Proactively initiates outbound reminder and follow-up campaigns.
In production this drives real telephony (Twilio/Exotel); here it logs to console.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta

from scheduler.appointment_engine import AppointmentEngine

logger = logging.getLogger("2care.campaign")

CAMPAIGN_MESSAGES = {
    "reminder": {
        "en": "Hello {name}, this is 2Care reminding you about your appointment with {doctor} tomorrow at {time}. Reply to confirm, reschedule, or cancel.",
        "hi": "नमस्ते {name}, यह 2Care का रिमाइंडर है। कल {time} बजे {doctor} के साथ आपका अपॉइंटमेंट है।",
        "ta": "வணக்கம் {name}, நாளை {time} மணிக்கு {doctor} உடன் உங்கள் சந்திப்பு இருக்கிறது என 2Care நினைவூட்டுகிறது.",
    },
    "followup": {
        "en": "Hello {name}, hope you are feeling better after your visit with {doctor}. Would you like to schedule a follow-up?",
        "hi": "नमस्ते {name}, {doctor} के साथ आपकी विजिट के बाद आप कैसा महसूस कर रहे हैं? क्या आप फॉलो-अप शेड्यूल करना चाहेंगे?",
        "ta": "வணக்கம் {name}, {doctor} உடனான சந்திப்பிற்குப் பிறகு நலமாக இருக்கிறீர்களா? ஒரு தொடர்ச்சியான சந்திப்பு வேண்டுமா?",
    },
}


class CampaignScheduler:
    def __init__(self, appointment_engine: AppointmentEngine):
        self.engine = appointment_engine
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._background_loop())
        logger.info("📅 Campaign scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("📅 Campaign scheduler stopped")

    async def _background_loop(self):
        """Check every hour and trigger reminder campaigns for tomorrow's appointments."""
        while self._running:
            try:
                await self.run_campaign("reminder")
            except Exception as e:
                logger.exception(f"Campaign loop error: {e}")
            await asyncio.sleep(3600)

    async def run_campaign(self, campaign_type: str):
        logger.info(f"📣 Running campaign: {campaign_type}")
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        # In a real system we'd query all patients with appointments tomorrow.
        # Here we iterate all stored appointments.
        appointments = [
            appt for appt in self.engine._appointments.values()
            if appt["date"] == tomorrow and appt["status"] == "confirmed"
        ]

        for appt in appointments:
            await self._dispatch(appt, campaign_type)

    async def _dispatch(self, appointment: dict, campaign_type: str):
        """Dispatch an outbound call/message for this appointment."""
        lang = "en"  # Would be loaded from patient profile in production
        template = CAMPAIGN_MESSAGES.get(campaign_type, {}).get(lang, "")
        message = template.format(
            name=appointment.get("patient_id", "Patient"),
            doctor=appointment.get("doctor_name", "your doctor"),
            time=appointment.get("time", ""),
        )

        # ── Production hook ──────────────────────────────────────────────────
        # await telephony_client.initiate_call(
        #     patient_id=appointment["patient_id"],
        #     message=message,
        #     callback_websocket="/ws/voice/{patient_id}"
        # )
        # ─────────────────────────────────────────────────────────────────────

        logger.info(
            f"📞 Outbound [{campaign_type}] → patient={appointment['patient_id']} "
            f"| appt={appointment['id']} | msg='{message}'"
        )
