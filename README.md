# 2Care.ai Voice Agent

Real-time voice AI for clinical appointment booking. Speaks English, Hindi, and Tamil.

Built in ~2 days as an assignment. Honest about what's prod-ready vs what's a stub.

---

## What it does

- Patient speaks → Whisper transcribes → Claude reasons + calls tools → TTS replies
- Books, cancels, reschedules appointments; detects conflicts; suggests alternatives
- Detects language per utterance (Unicode script fast-path, ML fallback)
- Remembers conversation context within a session; persists language preference across sessions
- Outbound reminder script (`campaign.py`) for proactive patient follow-ups

Demo works without a backend — open `frontend/index.html` directly in a browser.

---

## Structure

```
main.py                 FastAPI server + WebSocket pipeline
agent/core.py           STT, language detection, LLM loop, TTS — all in one file
scheduler/appointments.py   Booking logic, conflict detection, slot management
memory/store.py         Session history (in-memory TTL) + patient profiles (JSON)
campaign.py             Outbound reminder script (run standalone)
frontend/index.html     Demo UI with live latency display
tests/test_main.py      Tests for booking, conflict, language detection, memory
```

I kept it flat on purpose. Splitting each service into its own module and subpackage before there's a reason to is how you get 12 files that each do one thing but none of them do anything useful on their own.

---

## Setup

```bash
pip install -r requirements.txt

# copy and fill in your keys
cp .env.example .env

# run
uvicorn main:app --reload --port 8000

# open demo
open frontend/index.html
```

Set `MOCK_AUDIO=1` to run without real API keys — STT returns a canned transcript and TTS returns a silent MP3.

---

## Latency

Measured per turn, logged to console, shown live in the UI.

```
[abc12345] 318ms  stt=92 lang=8 agent=172 tts=46  ✓
```

Target is < 450ms. Typical is 280–360ms with the API in a low-latency region.

| Stage | Why it's fast |
|-------|--------------|
| STT (Whisper-1) | Language hint skips Whisper's internal detection pass |
| Language detect | Unicode block check runs in < 1ms for Hindi/Tamil |
| Agent (Claude) | claude-sonnet-4, max_tokens=512, tool loop exits on first `end_turn` |
| TTS (OpenAI tts-1) | `tts-1` not `tts-1-hd`; speed=1.05 |

---

## How the agent works

Claude gets the conversation history, a system prompt (built fresh each turn with patient context + language instruction), and 5 tools. It calls tools until it has enough to give a final reply.

The reasoning trace is sent back to the client alongside the audio — you can see exactly what tool was called and what it returned.

```
user: "Book a cardiologist for tomorrow"
→ tool: check_slots(speciality="cardiologist", date="tomorrow")
← {free_slots: ["10:00", "14:00", "16:00"]}
agent: "Dr. Anjali Sharma is free tomorrow at 10:00, 14:00, or 16:00. Which works?"
```

---

## Multilingual

| Language | STT hint | TTS | Detection |
|----------|----------|-----|-----------|
| English | `en` | OpenAI nova | default |
| Hindi | `hi` | OpenAI nova | Devanagari block U+0900–U+097F |
| Tamil | `ta` | gTTS | Tamil block U+0B80–U+0BFF |

Language is detected per utterance and persisted to the patient profile. The system prompt is rebuilt in that language every turn — Claude's multilingual capability handles the rest without prompt magic.

---

## Memory

**Session memory**: plain dict with a 30-min TTL. Stores the conversation messages list, passed to the LLM as history every turn. Cleared when the WebSocket closes.

**Persistent memory**: JSON file (`patient_profiles.json`). Stores preferred language and last doctor. Updated on every language switch. In production this would be a DB row.

I considered Redis but it adds an infra dependency without changing the interface — the dict has the same API. Easy swap when it matters.

---

## Scheduling logic

- Slot key: `(doctor_id, date, time)` — checked before every booking
- Past-time: `datetime.now()` comparison before confirming
- Conflict: returns up to 3 alternatives from the same doctor's free slots
- Cancel: frees the slot so it becomes available again
- Reschedule: atomic swap of old/new slot keys

---

## Outbound campaigns

`campaign.py` is a standalone script that reads tomorrow's confirmed appointments and prints the call script in the patient's preferred language. In production you'd replace the `print()` with a telephony API call (Twilio, Exotel, etc.) and wire the response back to the WebSocket endpoint.

---

## What's not production-ready

- Appointment store is in-memory — restarts lose all bookings
- No auth on the WebSocket endpoint
- Single process — no horizontal scaling
- VAD is client-side (user signals utterance end) — not server-side voice activity detection

None of these are hard to fix; they just weren't the point of this assignment.
