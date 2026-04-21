"""
2Care.ai Voice AI Agent — Main Backend Server
Real-time multilingual clinical appointment booking via WebSocket voice pipeline.
"""

import asyncio
import json
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from agent.orchestrator import AgentOrchestrator
from memory.session import SessionMemory
from memory.persistent import PersistentMemory
from services.stt.whisper_stt import SpeechToText
from services.tts.tts_engine import TextToSpeech
from services.language.detector import LanguageDetector
from scheduler.appointment_engine import AppointmentEngine
from scheduler.campaign import CampaignScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("2care.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 2Care.ai Voice Agent starting up...")
    app.state.session_memory = SessionMemory()
    app.state.persistent_memory = PersistentMemory()
    app.state.appointment_engine = AppointmentEngine()
    app.state.campaign_scheduler = CampaignScheduler(app.state.appointment_engine)
    await app.state.campaign_scheduler.start()
    logger.info("✅ All services initialized")
    yield
    logger.info("🛑 Shutting down...")
    await app.state.campaign_scheduler.stop()


app = FastAPI(
    title="2Care.ai Voice Agent",
    description="Real-Time Multilingual Voice AI for Clinical Appointment Booking",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "running", "service": "2care-voice-agent", "version": "1.0.0"}


@app.get("/appointments/{patient_id}")
async def get_appointments(patient_id: str):
    engine: AppointmentEngine = app.state.appointment_engine
    return {"patient_id": patient_id, "appointments": engine.get_patient_appointments(patient_id)}


@app.get("/doctors")
async def list_doctors():
    return {"doctors": app.state.appointment_engine.list_doctors()}


@app.get("/doctors/{doctor_id}/slots")
async def get_slots(doctor_id: str, date: Optional[str] = None):
    engine: AppointmentEngine = app.state.appointment_engine
    slots = engine.get_available_slots(doctor_id, date)
    return {"doctor_id": doctor_id, "date": date, "available_slots": slots}


@app.post("/campaigns/trigger")
async def trigger_campaign(background_tasks: BackgroundTasks, campaign_type: str = "reminder"):
    scheduler: CampaignScheduler = app.state.campaign_scheduler
    background_tasks.add_task(scheduler.run_campaign, campaign_type)
    return {"status": "triggered", "type": campaign_type}


@app.get("/metrics")
async def get_metrics():
    return app.state.session_memory.get_metrics()


# ── WebSocket Voice Pipeline ───────────────────────────────────────────────────

@app.websocket("/ws/voice/{patient_id}")
async def voice_websocket(websocket: WebSocket, patient_id: str):
    """
    Binary frames  → raw PCM audio chunks from client microphone.
    Text frames    → JSON control messages (start / end_utterance / end_session).

    Server replies:
      ← binary audio (TTS response)
      ← JSON { type: "transcript" | "response" | "latency" | "error" }
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"🔌 WS connected  patient={patient_id}  session={session_id}")

    session_mem: SessionMemory = app.state.session_memory
    persistent_mem: PersistentMemory = app.state.persistent_memory
    appointment_engine: AppointmentEngine = app.state.appointment_engine

    patient_profile = persistent_mem.load_profile(patient_id)
    detected_language = patient_profile.get("preferred_language", "en")

    stt = SpeechToText()
    tts = TextToSpeech()
    lang_detector = LanguageDetector()
    orchestrator = AgentOrchestrator(
        appointment_engine=appointment_engine,
        session_memory=session_mem,
        persistent_memory=persistent_mem,
        session_id=session_id,
        patient_id=patient_id,
    )

    audio_buffer: list[bytes] = []

    try:
        # Greet the patient
        greeting = orchestrator.get_greeting(detected_language, patient_profile)
        greeting_audio = await tts.synthesize(greeting, detected_language)
        await websocket.send_bytes(greeting_audio)
        await websocket.send_text(json.dumps({"type": "transcript", "speaker": "agent", "text": greeting}))

        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                audio_buffer.append(message["bytes"])

            elif "text" in message and message["text"]:
                control = json.loads(message["text"])

                if control.get("type") == "end_utterance" and audio_buffer:
                    t_start = time.perf_counter()

                    # 1 — STT
                    t0 = time.perf_counter()
                    raw_audio = b"".join(audio_buffer)
                    audio_buffer = []
                    transcript = await stt.transcribe(raw_audio, hint_language=detected_language)
                    stt_ms = (time.perf_counter() - t0) * 1000

                    if not transcript.strip():
                        continue

                    await websocket.send_text(json.dumps({
                        "type": "transcript", "speaker": "user", "text": transcript,
                    }))

                    # 2 — Language detection
                    t0 = time.perf_counter()
                    detected_language = lang_detector.detect(transcript)
                    lang_ms = (time.perf_counter() - t0) * 1000
                    persistent_mem.update_language(patient_id, detected_language)

                    # 3 — Agent reasoning + tool orchestration
                    t0 = time.perf_counter()
                    response_text, reasoning_trace = await orchestrator.process(transcript, detected_language)
                    agent_ms = (time.perf_counter() - t0) * 1000

                    # 4 — TTS
                    t0 = time.perf_counter()
                    response_audio = await tts.synthesize(response_text, detected_language)
                    tts_ms = (time.perf_counter() - t0) * 1000

                    total_ms = (time.perf_counter() - t_start) * 1000

                    await websocket.send_bytes(response_audio)
                    await websocket.send_text(json.dumps({
                        "type": "response",
                        "text": response_text,
                        "language": detected_language,
                        "reasoning_trace": reasoning_trace,
                    }))

                    latency_payload = {
                        "type": "latency",
                        "total_ms": round(total_ms, 1),
                        "within_target": total_ms < 450,
                        "breakdown": {
                            "stt_ms": round(stt_ms, 1),
                            "lang_ms": round(lang_ms, 1),
                            "agent_ms": round(agent_ms, 1),
                            "tts_ms": round(tts_ms, 1),
                        },
                    }
                    await websocket.send_text(json.dumps(latency_payload))

                    logger.info(
                        f"⏱  total={total_ms:.0f}ms "
                        f"(STT={stt_ms:.0f} LANG={lang_ms:.0f} "
                        f"AGENT={agent_ms:.0f} TTS={tts_ms:.0f}) "
                        f"{'✅' if total_ms < 450 else '⚠️ OVER TARGET'}"
                    )
                    session_mem.log_latency(session_id, latency_payload)

                elif control.get("type") == "end_session":
                    break

    except WebSocketDisconnect:
        logger.info(f"🔌 WS disconnected  patient={patient_id}")
    except Exception as e:
        logger.exception(f"❌ WS error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        session_mem.clear_session(session_id)
        logger.info(f"🧹 Session cleaned up: {session_id}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
