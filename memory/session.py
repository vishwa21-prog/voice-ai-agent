"""
Session Memory
Stores short-lived per-session state: conversation history, current intent, latency logs.
Uses an in-memory dict with TTL (swap .store for Redis in production).
"""

import time
import logging
from typing import Any

logger = logging.getLogger("2care.memory.session")

SESSION_TTL_SECONDS = 1800  # 30 minutes


class SessionMemory:
    def __init__(self):
        # { session_id: { "data": {...}, "expires_at": float } }
        self._store: dict[str, dict] = {}
        self._latency_log: list[dict] = []

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _touch(self, session_id: str):
        if session_id not in self._store:
            self._store[session_id] = {"data": {}, "expires_at": 0.0}
        self._store[session_id]["expires_at"] = time.time() + SESSION_TTL_SECONDS

    def _get(self, session_id: str) -> dict:
        entry = self._store.get(session_id)
        if not entry:
            return {}
        if time.time() > entry["expires_at"]:
            del self._store[session_id]
            return {}
        return entry["data"]

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_history(self, session_id: str) -> list[dict]:
        return self._get(session_id).get("history", [])

    def save_history(self, session_id: str, history: list[dict]):
        self._touch(session_id)
        self._store[session_id]["data"]["history"] = history

    def get_context(self, session_id: str) -> dict:
        return self._get(session_id).get("context", {})

    def update_context(self, session_id: str, updates: dict):
        self._touch(session_id)
        ctx = self._store[session_id]["data"].setdefault("context", {})
        ctx.update(updates)

    def clear_session(self, session_id: str):
        self._store.pop(session_id, None)
        logger.debug(f"Session cleared: {session_id}")

    def log_latency(self, session_id: str, payload: dict):
        self._latency_log.append({"session_id": session_id, **payload})
        # Keep only last 1000 entries
        if len(self._latency_log) > 1000:
            self._latency_log = self._latency_log[-1000:]

    def get_metrics(self) -> dict:
        if not self._latency_log:
            return {"total_calls": 0}
        totals = [e["total_ms"] for e in self._latency_log]
        within = [e for e in self._latency_log if e.get("within_target")]
        return {
            "total_calls": len(totals),
            "avg_latency_ms": round(sum(totals) / len(totals), 1),
            "min_latency_ms": round(min(totals), 1),
            "max_latency_ms": round(max(totals), 1),
            "within_450ms_pct": round(len(within) / len(totals) * 100, 1),
            "active_sessions": len(self._store),
        }
