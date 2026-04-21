"""
2Care.ai — Voice Agent Server
Run: uvicorn main:app --reload --port 8000
"""

import asyncio, json, time, uuid, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from agent.core import VoiceAgent
from scheduler.appointments import AppointmentStore
from memory.store import MemoryStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.appointments = AppointmentStore()
    app.state.memory = MemoryStore()
    log.info("Server ready")
    yield


app = FastAPI(title="2Care Voice Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/appointments/{patient_id}")
def get_appointments(patient_id: str):
    return app.state.appointments.get_for_patient(patient_id)


@app.get("/doctors")
def list_doctors():
    return app.state.appointments.list_doctors()


# ── WebSocket voice pipeline ───────────────────────────────────────────────────

@app.websocket("/ws/{patient_id}")
async def voice_ws(ws: WebSocket, patient_id: str):
    await ws.accept()
    session_id = str(uuid.uuid4())[:8]
    log.info(f"[{session_id}] connected patient={patient_id}")

    agent = VoiceAgent(
        patient_id=patient_id,
        session_id=session_id,
        appointments=app.state.appointments,
        memory=app.state.memory,
    )

    audio_buf: list[bytes] = []

    try:
        # Greet
        greeting = agent.greet()
        await ws.send_text(json.dumps({"type": "agent", "text": greeting}))

        while True:
            msg = await ws.receive()

            if "bytes" in msg and msg["bytes"]:
                audio_buf.append(msg["bytes"])

            elif "text" in msg and msg["text"]:
                ctrl = json.loads(msg["text"])

                if ctrl["type"] == "utterance_end" and audio_buf:
                    t0 = time.perf_counter()

                    # 1. STT
                    t_stt = time.perf_counter()
                    audio = b"".join(audio_buf); audio_buf = []
                    transcript = await agent.stt(audio)
                    stt_ms = (time.perf_counter() - t_stt) * 1000

                    if not transcript:
                        continue

                    await ws.send_text(json.dumps({"type": "user", "text": transcript}))

                    # 2. Detect language
                    t_lang = time.perf_counter()
                    lang = agent.detect_language(transcript)
                    lang_ms = (time.perf_counter() - t_lang) * 1000

                    # 3. Agent reply
                    t_agent = time.perf_counter()
                    reply, trace = await agent.think(transcript, lang)
                    agent_ms = (time.perf_counter() - t_agent) * 1000

                    # 4. TTS
                    t_tts = time.perf_counter()
                    audio_out = await agent.tts(reply, lang)
                    tts_ms = (time.perf_counter() - t_tts) * 1000

                    total_ms = (time.perf_counter() - t0) * 1000

                    await ws.send_bytes(audio_out)
                    await ws.send_text(json.dumps({
                        "type": "agent", "text": reply, "lang": lang, "trace": trace,
                        "latency": {
                            "total": round(total_ms),
                            "stt": round(stt_ms),
                            "lang": round(lang_ms),
                            "agent": round(agent_ms),
                            "tts": round(tts_ms),
                            "ok": total_ms < 450,
                        },
                    }))

                    log.info(
                        f"[{session_id}] {total_ms:.0f}ms "
                        f"stt={stt_ms:.0f} lang={lang_ms:.0f} agent={agent_ms:.0f} tts={tts_ms:.0f} "
                        f"{'✓' if total_ms < 450 else '✗ SLOW'}"
                    )

                elif ctrl["type"] == "end":
                    break

    except WebSocketDisconnect:
        log.info(f"[{session_id}] disconnected")
    finally:
        app.state.memory.end_session(session_id)
