"""
Agent core — STT, language detection, LLM reasoning, TTS in one place.
Intentionally not split into 6 files. A real engineer would start here.
"""

import io, os, json, logging
from anthropic import Anthropic

from scheduler.appointments import AppointmentStore
from memory.store import MemoryStore

log = logging.getLogger(__name__)

# ── Language helpers ───────────────────────────────────────────────────────────

def _script_detect(text: str) -> str:
    """Detect Hindi/Tamil by Unicode block before touching any ML library."""
    for ch in text:
        c = ord(ch)
        if 0x0900 <= c <= 0x097F: return "hi"
        if 0x0B80 <= c <= 0x0BFF: return "ta"
    return "en"

GREETINGS = {
    "en": "Hi! I'm your 2Care assistant. How can I help with your appointment today?",
    "hi": "नमस्ते! मैं आपका 2Care सहायक हूँ। आज अपॉइंटमेंट के बारे में कैसे मदद करूँ?",
    "ta": "வணக்கம்! நான் உங்கள் 2Care உதவியாளர். சந்திப்பு பற்றி எவ்வாறு உதவலாம்?",
}

RETURNING = {
    "en": "Welcome back, {name}! What can I help you with today?",
    "hi": "स्वागत है, {name}! आज क्या मदद चाहिए?",
    "ta": "மீண்டும் வரவேற்கிறோம், {name}! இன்று எப்படி உதவலாம்?",
}


# ── Tool definitions (sent to Claude) ─────────────────────────────────────────

TOOLS = [
    {
        "name": "check_slots",
        "description": "Check available appointment slots for a doctor/speciality on a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speciality": {"type": "string", "description": "e.g. cardiologist"},
                "doctor_id": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD or 'tomorrow'"},
            },
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment. Always check slots first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string", "description": "HH:MM"},
                "reason": {"type": "string"},
            },
            "required": ["doctor_id", "date", "time"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment.",
        "input_schema": {
            "type": "object",
            "properties": {"appointment_id": {"type": "string"}},
            "required": ["appointment_id"],
        },
    },
    {
        "name": "reschedule_appointment",
        "description": "Move an appointment to a new date/time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "new_date": {"type": "string"},
                "new_time": {"type": "string"},
            },
            "required": ["appointment_id", "new_date", "new_time"],
        },
    },
    {
        "name": "list_appointments",
        "description": "Get upcoming appointments for the patient.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ── System prompt ──────────────────────────────────────────────────────────────

def build_prompt(lang: str, profile: dict) -> str:
    from datetime import date
    today = date.today().strftime("%A, %d %B %Y")

    lang_line = {
        "en": "Reply in English.",
        "hi": "हिंदी में जवाब दें।",
        "ta": "தமிழில் பதிலளிக்கவும்.",
    }.get(lang, "Reply in English.")

    history_line = ""
    if profile.get("last_doctor"):
        history_line = f"Patient's last visit was with {profile['last_doctor']}."

    return f"""You are a clinical appointment assistant for 2Care.ai.
Today is {today}. {lang_line}

{history_line}

Rules:
- Keep replies SHORT (1-3 sentences max — this is voice, not chat)
- Always check availability before booking
- Offer alternatives when a slot is taken
- Confirm details before finalising any booking
- Never invent appointment data — use the tools

If unsure, ask one focused question."""


# ── Agent class ────────────────────────────────────────────────────────────────

class VoiceAgent:
    def __init__(self, patient_id: str, session_id: str,
                 appointments: AppointmentStore, memory: MemoryStore):
        self.patient_id = patient_id
        self.session_id = session_id
        self.appointments = appointments
        self.memory = memory
        self.client = Anthropic()

        # Lazy-import optional deps
        self._openai = None

    # ── Greeting ───────────────────────────────────────────────────────────────

    def greet(self) -> str:
        profile = self.memory.get_profile(self.patient_id)
        lang = profile.get("lang", "en")
        name = profile.get("name")
        if name:
            return RETURNING[lang].format(name=name)
        return GREETINGS[lang]

    # ── Language detection ────────────────────────────────────────────────────

    def detect_language(self, text: str) -> str:
        lang = _script_detect(text)
        if lang != "en":
            self.memory.set_lang(self.patient_id, lang)
            return lang

        # fallback: langdetect (optional)
        try:
            from langdetect import detect
            detected = detect(text).split("-")[0]
            if detected in ("en", "hi", "ta"):
                self.memory.set_lang(self.patient_id, detected)
                return detected
        except Exception:
            pass
        return "en"

    # ── STT ───────────────────────────────────────────────────────────────────

    async def stt(self, audio_bytes: bytes) -> str:
        if os.getenv("MOCK_AUDIO"):
            return "Book an appointment with a cardiologist tomorrow"

        if self._openai is None:
            import openai
            self._openai = openai.AsyncOpenAI()

        buf = io.BytesIO(audio_bytes)
        buf.name = "audio.webm"
        resp = await self._openai.audio.transcriptions.create(
            model="whisper-1", file=buf, response_format="text"
        )
        return resp.strip()

    # ── TTS ───────────────────────────────────────────────────────────────────

    async def tts(self, text: str, lang: str) -> bytes:
        if os.getenv("MOCK_AUDIO"):
            return b"\xff\xfb\x90\x00" + b"\x00" * 200  # silent mp3

        # Tamil: gTTS (better Tamil support than OpenAI TTS)
        if lang == "ta":
            return await self._gtts(text)

        if self._openai is None:
            import openai
            self._openai = openai.AsyncOpenAI()

        resp = await self._openai.audio.speech.create(
            model="tts-1", voice="nova", input=text,
            response_format="mp3", speed=1.05,
        )
        return resp.content

    async def _gtts(self, text: str) -> bytes:
        import asyncio
        from gtts import gTTS
        def _gen():
            buf = io.BytesIO()
            gTTS(text=text, lang="ta", slow=False).write_to_fp(buf)
            return buf.getvalue()
        return await asyncio.get_event_loop().run_in_executor(None, _gen)

    # ── Think: LLM reasoning loop ─────────────────────────────────────────────

    async def think(self, user_text: str, lang: str) -> tuple[str, list]:
        profile = self.memory.get_profile(self.patient_id)
        history = self.memory.get_history(self.session_id)

        history.append({"role": "user", "content": user_text})

        trace = []
        messages = list(history)

        while True:
            resp = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=build_prompt(lang, profile),
                tools=TOOLS,
                messages=messages,
            )

            text_parts = [b.text for b in resp.content if b.type == "text" and b.text]

            if resp.stop_reason == "tool_use":
                tool_blocks = [b for b in resp.content if b.type == "tool_use"]
                messages.append({"role": "assistant", "content": resp.content})

                results = []
                for tb in tool_blocks:
                    result = self._run_tool(tb.name, tb.input)
                    trace.append({"tool": tb.name, "in": tb.input, "out": result})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": json.dumps(result),
                    })
                messages.append({"role": "user", "content": results})

            else:
                reply = " ".join(text_parts).strip() or self._fallback(lang)
                history.append({"role": "assistant", "content": reply})
                self.memory.save_history(self.session_id, history)
                return reply, trace

    def _run_tool(self, name: str, args: dict) -> dict:
        log.info(f"  tool → {name}({args})")
        if name == "check_slots":
            return self.appointments.check_slots(
                args.get("speciality"), args.get("doctor_id"), args.get("date")
            )
        if name == "book_appointment":
            return self.appointments.book(
                self.patient_id, args["doctor_id"], args["date"], args["time"],
                args.get("reason", "")
            )
        if name == "cancel_appointment":
            return self.appointments.cancel(args["appointment_id"])
        if name == "reschedule_appointment":
            return self.appointments.reschedule(
                args["appointment_id"], args["new_date"], args["new_time"]
            )
        if name == "list_appointments":
            return {"appointments": self.appointments.get_for_patient(self.patient_id)}
        return {"error": f"unknown tool: {name}"}

    def _fallback(self, lang: str) -> str:
        return {
            "en": "Sorry, could you repeat that?",
            "hi": "माफ करें, क्या दोबारा कह सकते हैं?",
            "ta": "மன்னிக்கவும், மீண்டும் சொல்லுங்கள்.",
        }.get(lang, "Sorry, could you repeat that?")
