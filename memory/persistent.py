"""
Persistent Memory
Stores long-term patient profiles: name, language preference, appointment history.
Uses a JSON file store (swap for PostgreSQL/Redis in production).
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("2care.memory.persistent")

STORE_PATH = Path("./data/patient_profiles.json")


# Seed data — simulates existing patient records
SEED_PROFILES = {
    "patient_001": {
        "id": "patient_001",
        "name": "Ravi Kumar",
        "preferred_language": "ta",
        "preferred_doctor": "dr_sharma",
        "past_appointments": [
            {"doctor_name": "Dr. Anjali Sharma", "date": "2025-12-10", "speciality": "cardiologist"}
        ],
    },
    "patient_002": {
        "id": "patient_002",
        "name": "Priya Singh",
        "preferred_language": "hi",
        "preferred_doctor": None,
        "past_appointments": [],
    },
}


class PersistentMemory:
    def __init__(self):
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not STORE_PATH.exists():
            STORE_PATH.write_text(json.dumps(SEED_PROFILES, indent=2))
        self._load()

    def _load(self):
        try:
            with open(STORE_PATH) as f:
                self._profiles: dict = json.load(f)
        except Exception:
            self._profiles = dict(SEED_PROFILES)

    def _save(self):
        with open(STORE_PATH, "w") as f:
            json.dump(self._profiles, f, indent=2)

    def load_profile(self, patient_id: str) -> dict:
        return self._profiles.get(patient_id, {})

    def update_language(self, patient_id: str, language: str):
        if patient_id not in self._profiles:
            self._profiles[patient_id] = {"id": patient_id}
        self._profiles[patient_id]["preferred_language"] = language
        self._save()
        logger.debug(f"Updated language for {patient_id}: {language}")

    def update_appointment_history(self, patient_id: str, appointment: dict):
        if patient_id not in self._profiles:
            self._profiles[patient_id] = {"id": patient_id, "past_appointments": []}
        self._profiles[patient_id].setdefault("past_appointments", []).append(appointment)
        # Keep last 10
        self._profiles[patient_id]["past_appointments"] = \
            self._profiles[patient_id]["past_appointments"][-10:]
        self._save()

    def upsert_profile(self, patient_id: str, updates: dict):
        profile = self._profiles.setdefault(patient_id, {"id": patient_id})
        profile.update(updates)
        self._save()
