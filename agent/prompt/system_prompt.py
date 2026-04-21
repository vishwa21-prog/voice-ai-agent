"""
System prompt builder.
Injects patient context and language instructions into the LLM system prompt.
"""

from datetime import date


LANGUAGE_INSTRUCTION = {
    "en": "Respond in English. Be concise and warm.",
    "hi": "हिंदी में जवाब दें। संक्षिप्त और सहायक रहें।",
    "ta": "தமிழில் பதிலளிக்கவும். சுருக்கமாகவும் அன்பாகவும் இருங்கள்.",
}


def build_system_prompt(language: str, patient_profile: dict, session_context: dict) -> str:
    today = date.today().strftime("%A, %d %B %Y")
    lang_instruction = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["en"])

    name_line = f"Patient name: {patient_profile['name']}" if patient_profile.get("name") else ""
    history_line = ""
    if patient_profile.get("past_appointments"):
        last = patient_profile["past_appointments"][-1]
        history_line = f"Last appointment: {last.get('doctor_name', 'unknown')} on {last.get('date', 'unknown')}"

    pref_doctor_line = ""
    if patient_profile.get("preferred_doctor"):
        pref_doctor_line = f"Preferred doctor: {patient_profile['preferred_doctor']}"

    pending_intent = ""
    if session_context.get("pending_intent"):
        pending_intent = f"Current pending intent in this session: {session_context['pending_intent']}"

    return f"""You are a helpful, empathetic healthcare appointment assistant for 2Care.ai.
Today's date is {today}.

{lang_instruction}

Patient profile:
{name_line}
{history_line}
{pref_doctor_line}
{pending_intent}

Your responsibilities:
1. Help patients book, reschedule, or cancel clinical appointments.
2. Always check doctor availability before confirming a booking.
3. If a requested slot is unavailable, proactively suggest 2-3 alternatives.
4. Never double-book. Never book appointments in the past.
5. Confirm all booking details (doctor, date, time) before finalising.
6. Keep responses SHORT — you are speaking over voice, not writing an essay.
7. If the patient's intent is unclear, ask one focused clarifying question.
8. Always use the appropriate tools — never invent appointment data.

Tone: Warm, professional, efficient. Maximum 2-3 sentences per response.
""".strip()
