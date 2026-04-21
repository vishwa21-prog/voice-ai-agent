"""
Test suite for 2Care.ai Voice Agent
Tests appointment engine, conflict detection, language detection, memory.
"""

import pytest
from datetime import date, timedelta

from scheduler.appointment_engine import AppointmentEngine, _resolve_date
from services.language.detector import LanguageDetector
from memory.session import SessionMemory
from memory.persistent import PersistentMemory


# ── Date Resolution ────────────────────────────────────────────────────────────

def test_resolve_tomorrow():
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert _resolve_date("tomorrow") == tomorrow


def test_resolve_today():
    today = date.today().strftime("%Y-%m-%d")
    assert _resolve_date("today") == today


def test_resolve_iso():
    assert _resolve_date("2026-06-15") == "2026-06-15"


# ── Appointment Engine ─────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return AppointmentEngine()


def test_list_doctors(engine):
    doctors = engine.list_doctors()
    assert len(doctors) > 0
    assert all("id" in d and "speciality" in d for d in doctors)


def test_find_by_speciality(engine):
    results = engine.find_doctors_by_speciality("cardiologist")
    assert len(results) >= 1
    assert results[0]["speciality"] == "cardiologist"


def test_book_appointment(engine):
    future_date = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")
    result = engine.book_appointment(
        patient_id="test_patient",
        doctor_id="dr_sharma",
        date_str=future_date,
        time_slot="10:00",
    )
    assert result["success"] is True
    assert "appointment" in result
    assert result["appointment"]["status"] == "confirmed"


def test_double_booking_conflict(engine):
    future_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
    r1 = engine.book_appointment("p1", "dr_sharma", future_date, "11:00")
    r2 = engine.book_appointment("p2", "dr_sharma", future_date, "11:00")
    assert r1["success"] is True
    assert r2["success"] is False
    assert r2["error"] == "slot_conflict"
    assert len(r2["alternatives"]) > 0


def test_cancel_appointment(engine):
    future_date = (date.today() + timedelta(days=4)).strftime("%Y-%m-%d")
    book = engine.book_appointment("p1", "dr_patel", future_date, "14:00")
    appt_id = book["appointment"]["id"]
    cancel = engine.cancel_appointment(appt_id)
    assert cancel["success"] is True


def test_cancel_nonexistent(engine):
    result = engine.cancel_appointment("FAKE-ID")
    assert result["success"] is False
    assert result["error"] == "not_found"


def test_reschedule_appointment(engine):
    d1 = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
    d2 = (date.today() + timedelta(days=6)).strftime("%Y-%m-%d")
    book = engine.book_appointment("p1", "dr_menon", d1, "09:30")
    appt_id = book["appointment"]["id"]
    result = engine.reschedule_appointment(appt_id, d2, "15:00")
    assert result["success"] is True
    assert result["appointment"]["date"] == d2
    assert result["appointment"]["time"] == "15:00"


def test_available_slots_reduced_after_booking(engine):
    future_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    before = engine.get_available_slots("dr_kumar", future_date)
    engine.book_appointment("p1", "dr_kumar", future_date, "09:00")
    after = engine.get_available_slots("dr_kumar", future_date)
    assert len(after) == len(before) - 1
    assert "09:00" not in after


# ── Language Detection ─────────────────────────────────────────────────────────

@pytest.fixture
def detector():
    return LanguageDetector()


def test_detect_hindi(detector):
    lang = detector.detect("मुझे कल डॉक्टर से मिलना है")
    assert lang == "hi"


def test_detect_tamil(detector):
    lang = detector.detect("நாளை மருத்துவரை பார்க்க வேண்டும்")
    assert lang == "ta"


def test_detect_english(detector):
    lang = detector.detect("Book an appointment for tomorrow")
    assert lang == "en"


def test_detect_empty(detector):
    lang = detector.detect("")
    assert lang == "en"  # Safe default


# ── Session Memory ─────────────────────────────────────────────────────────────

def test_session_history():
    mem = SessionMemory()
    sid = "test-session-1"
    history = [{"role": "user", "content": "hello"}]
    mem.save_history(sid, history)
    assert mem.get_history(sid) == history


def test_session_context():
    mem = SessionMemory()
    sid = "test-session-2"
    mem.update_context(sid, {"pending_intent": "booking"})
    assert mem.get_context(sid)["pending_intent"] == "booking"


def test_session_clear():
    mem = SessionMemory()
    sid = "test-session-3"
    mem.save_history(sid, [{"role": "user", "content": "hi"}])
    mem.clear_session(sid)
    assert mem.get_history(sid) == []


def test_latency_metrics():
    mem = SessionMemory()
    mem.log_latency("s1", {"total_ms": 300, "within_target": True})
    mem.log_latency("s2", {"total_ms": 500, "within_target": False})
    metrics = mem.get_metrics()
    assert metrics["total_calls"] == 2
    assert metrics["within_450ms_pct"] == 50.0
