"""
Memory: session history (short-term) + patient profiles (long-term).
Simple dicts — no Redis needed to get the concept across.
"""

import json, time, logging
from pathlib import Path

log = logging.getLogger(__name__)

PROFILES_FILE = Path("./patient_profiles.json")
SESSION_TTL = 30 * 60  # 30 min

# Seed profiles so the demo shows returning-patient behaviour
SEED = {
    "patient_001": {"name": "Ravi Kumar",  "lang": "ta", "last_doctor": "Dr. Anjali Sharma"},
    "patient_002": {"name": "Priya Singh", "lang": "hi", "last_doctor": None},
}


class MemoryStore:
    def __init__(self):
        self._sessions: dict[str, dict] = {}  # session_id → {history, expires}
        if PROFILES_FILE.exists():
            self._profiles: dict = json.loads(PROFILES_FILE.read_text())
        else:
            self._profiles = dict(SEED)
            self._save()

    # ── Profiles ──────────────────────────────────────────────────────────────

    def get_profile(self, patient_id: str) -> dict:
        return self._profiles.get(patient_id, {})

    def set_lang(self, patient_id: str, lang: str):
        self._profiles.setdefault(patient_id, {})["lang"] = lang
        self._save()

    def _save(self):
        PROFILES_FILE.write_text(json.dumps(self._profiles, indent=2))

    # ── Session history ───────────────────────────────────────────────────────

    def get_history(self, session_id: str) -> list:
        entry = self._sessions.get(session_id)
        if not entry or time.time() > entry["expires"]:
            return []
        return entry["history"]

    def save_history(self, session_id: str, history: list):
        self._sessions[session_id] = {
            "history": history,
            "expires": time.time() + SESSION_TTL,
        }

    def end_session(self, session_id: str):
        self._sessions.pop(session_id, None)
