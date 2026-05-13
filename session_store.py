from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
from typing import Callable, Literal


_USAGE_FILE = Path.home() / ".cardputer-daemon" / "usage.json"


def _read_usage() -> dict:
    """Load rate_limits written by the statusline script.

    Returns a compact dict with five_hour/seven_day percentages, or empty
    if the file is missing/unreadable. Compact keys keep the BLE payload small.
    """
    try:
        data = json.loads(_USAGE_FILE.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}
    out: dict = {}
    five = data.get("five_hour", {}).get("used_percentage")
    week = data.get("seven_day", {}).get("used_percentage")
    if isinstance(five, (int, float)):
        out["5h"] = round(five)
    if isinstance(week, (int, float)):
        out["7d"] = round(week)
    return out


HOOK_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
}


@dataclass
class Session:
    state: Literal["idle", "running"]
    cwd: str
    started_at: datetime
    last_seen: datetime

    def snapshot(self) -> dict[str, str]:
        return {
            "state": self.state,
            "cwd": self.cwd,
            "started_at": _isoformat(self.started_at),
            "last_seen": _isoformat(self.last_seen),
        }


class SessionStore:
    def __init__(
        self,
        now_fn: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(minutes=30),
    ) -> None:
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())
        self.ttl = ttl
        self.sessions: dict[str, Session] = {}
        self.tokens_today = 0
        self.entries_today = 0
        self.latest_event_msg = "idle"
        self.today_date = self._now().date()
        self._pending_notif: dict | None = None

    def apply_event(self, event: dict) -> bool:
        name = event.get("hook_event_name")
        sid = event.get("session_id")
        if name not in HOOK_EVENTS or not sid:
            return False

        now = self._now()
        self._reset_if_new_day(now)

        cwd = str(event.get("cwd") or "?")
        if sid not in self.sessions:
            self.sessions[sid] = Session(
                state="idle",
                cwd=cwd,
                started_at=now,
                last_seen=now,
            )
        else:
            session = self.sessions[sid]
            session.cwd = cwd
            session.last_seen = now

        session = self.sessions[sid]
        cwd_name = _basename(cwd)

        if name == "SessionStart":
            self.latest_event_msg = "\U0001f680 start " + cwd_name
        elif name == "UserPromptSubmit":
            session.state = "running"
            self.entries_today += 1
            self.latest_event_msg = "\U0001f916 working in " + cwd_name
        elif name == "Stop":
            if session.state == "running":
                self._pending_notif = {"t": "done", "p": cwd_name}
            session.state = "idle"
            self.latest_event_msg = "\u2726 done in " + cwd_name
        elif name == "SubagentStop":
            self.latest_event_msg = "\U0001fab6 subagent done"
        elif name == "SessionEnd":
            del self.sessions[sid]
            self.latest_event_msg = "\U0001f44b end " + cwd_name

        self.tokens_today += 1
        return True

    def prune_inactive(self) -> int:
        now = self._now()
        expired = [
            sid
            for sid, session in self.sessions.items()
            if now - session.last_seen > self.ttl
        ]
        for sid in expired:
            del self.sessions[sid]
        return len(expired)

    def compute_heartbeat(self) -> dict:
        running = sum(1 for session in self.sessions.values() if session.state == "running")
        total = len(self.sessions)
        hb: dict = {
            "msg": self.latest_event_msg,
            "total": total,
            "running": running,
            "coding_active": running > 0,
            "waiting": total - running,
            "tokens": self.tokens_today,
            "tokens_today": self.tokens_today,
            "entries": self.entries_today,
        }
        usage = _read_usage()
        if usage:
            hb["usage"] = usage
        if self._pending_notif is not None:
            hb["notif"] = self._pending_notif
            self._pending_notif = None
        return hb

    def snapshot_sessions(self) -> dict[str, dict[str, str]]:
        return {sid: session.snapshot() for sid, session in self.sessions.items()}

    def _now(self) -> datetime:
        now = self._now_fn()
        if now.tzinfo is None:
            return now.astimezone()
        return now

    def _reset_if_new_day(self, now: datetime) -> None:
        if now.date() > self.today_date:
            self.tokens_today = 0
            self.entries_today = 0
            self.today_date = now.date()


def _basename(path: str) -> str:
    name = os.path.basename(path.rstrip(os.sep))
    return name or "?"


def _isoformat(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")
