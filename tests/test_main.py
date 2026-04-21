"""
Tests for the appointment logic and language detection.
Focused on the actual tricky bits, not boilerplate.
"""

import pytest
from datetime import date, timedelta
from scheduler.appointments import AppointmentStore, _resolve_date
from agent.core import _script_detect
from memory.store import MemoryStore


# ── date resolution ────────────────────────────────────────────────────────────

def test_tomorrow():
    assert _resolve_date("tomorrow") == (date.today() + timedelta(1)).strftime("%Y-%m-%d")

def test_today():
    assert _resolve_date("today") == date.today().strftime("%Y-%m-%d")

def test_passthrough_iso():
    assert _resolve_date("2026-12-25") == "2026-12-25"


# ── language detection (script heuristic) ─────────────────────────────────────

def test_detect_hindi():
    assert _script_detect("मुझे कल डॉक्टर से मिलना है") == "hi"

def test_detect_tamil():
    assert _script_detect("நாளை மருத்துவரை பார்க்க வேண்டும்") == "ta"

def test_detect_english():
    assert _script_detect("Book a cardiologist for tomorrow") == "en"


# ── booking ───────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    return AppointmentStore()

def future(days=3):
    return (date.today() + timedelta(days)).strftime("%Y-%m-%d")

def test_book_ok(store):
    r = store.book("p1", "dr_sharma", future(), "10:00")
    assert r["success"]
    assert r["appointment"]["status"] == "confirmed"

def test_double_book_blocked(store):
    store.book("p1", "dr_sharma", future(4), "11:00")
    r = store.book("p2", "dr_sharma", future(4), "11:00")
    assert not r["success"]
    assert r["reason"] == "slot_taken"
    assert len(r["alternatives"]) > 0  # must suggest alternatives

def test_cancel_frees_slot(store):
    r = store.book("p1", "dr_patel", future(5), "14:00")
    appt_id = r["appointment"]["id"]
    store.cancel(appt_id)
    # slot should be free again
    slots = store.check_slots(doctor_id="dr_patel", date_str=future(5))
    assert "14:00" in slots["free_slots"]

def test_reschedule(store):
    r = store.book("p1", "dr_menon", future(6), "09:00")
    appt_id = r["appointment"]["id"]
    r2 = store.reschedule(appt_id, future(7), "15:00")
    assert r2["success"]
    assert r2["appointment"]["date"] == future(7)
    assert r2["appointment"]["time"] == "15:00"

def test_past_time_rejected(store):
    r = store.book("p1", "dr_iyer", "2020-01-01", "09:00")
    assert not r["success"]
    assert r["reason"] == "past_time"

def test_check_slots_by_speciality(store):
    r = store.check_slots(speciality="cardiologist", date_str=future(2))
    assert r["available"]
    assert "09:00" in r["free_slots"]


# ── memory ────────────────────────────────────────────────────────────────────

def test_session_roundtrip():
    mem = MemoryStore()
    history = [{"role": "user", "content": "hello"}]
    mem.save_history("s1", history)
    assert mem.get_history("s1") == history
    mem.end_session("s1")
    assert mem.get_history("s1") == []

def test_lang_persistence():
    mem = MemoryStore()
    mem.set_lang("test_patient", "ta")
    assert mem.get_profile("test_patient")["lang"] == "ta"
