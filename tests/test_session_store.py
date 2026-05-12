from __future__ import annotations

from datetime import datetime, timedelta, timezone

from session_store import SessionStore


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs) -> None:
        self.value += timedelta(**kwargs)


def event(name: str, sid: str = "s1", cwd: str = "/tmp/project") -> dict:
    return {
        "type": "hook",
        "hook_event_name": name,
        "session_id": sid,
        "cwd": cwd,
        "transcript_path": "/tmp/transcript.jsonl",
    }


def test_five_hook_events_in_order_update_counts_and_state() -> None:
    store = SessionStore()

    assert store.apply_event(event("SessionStart"))
    assert store.sessions["s1"].state == "idle"
    assert store.apply_event(event("UserPromptSubmit"))
    assert store.sessions["s1"].state == "running"
    assert store.apply_event(event("SubagentStop"))
    assert store.sessions["s1"].state == "running"
    assert store.apply_event(event("Stop"))
    assert store.sessions["s1"].state == "idle"
    assert store.apply_event(event("SessionEnd"))

    heartbeat = store.compute_heartbeat()
    assert heartbeat["total"] == 0
    assert heartbeat["running"] == 0
    assert heartbeat["waiting"] == 0
    assert heartbeat["tokens_today"] == 5
    assert heartbeat["entries"] == 1


def test_out_of_order_stop_then_session_start_upserts_unknown_session() -> None:
    store = SessionStore()

    assert store.apply_event(event("Stop", sid="late", cwd="/tmp/late"))
    assert store.sessions["late"].state == "idle"
    assert store.compute_heartbeat()["total"] == 1

    assert store.apply_event(event("SessionStart", sid="late", cwd="/tmp/late"))
    assert store.sessions["late"].state == "idle"
    assert store.compute_heartbeat()["tokens"] == 2


def test_daemon_restart_unknown_user_prompt_becomes_running() -> None:
    store = SessionStore()

    assert store.apply_event(event("UserPromptSubmit", sid="unknown", cwd="/tmp/work"))

    heartbeat = store.compute_heartbeat()
    assert store.sessions["unknown"].state == "running"
    assert heartbeat["total"] == 1
    assert heartbeat["running"] == 1
    assert heartbeat["entries"] == 1


def test_ttl_prune_removes_sessions_older_than_thirty_minutes() -> None:
    clock = Clock(datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc))
    store = SessionStore(now_fn=clock.now)
    assert store.apply_event(event("SessionStart", sid="old"))
    assert store.apply_event(event("SessionStart", sid="fresh"))

    store.sessions["old"].last_seen = clock.now() - timedelta(minutes=31)

    assert store.prune_inactive() == 1
    assert "old" not in store.sessions
    assert "fresh" in store.sessions


def test_cross_day_reset_clears_daily_counters_before_new_event() -> None:
    clock = Clock(datetime(2026, 5, 12, 23, 59, tzinfo=timezone.utc))
    store = SessionStore(now_fn=clock.now)
    assert store.apply_event(event("UserPromptSubmit", sid="s1"))
    assert store.compute_heartbeat()["tokens_today"] == 1
    assert store.compute_heartbeat()["entries"] == 1

    clock.advance(minutes=2)
    assert store.apply_event(event("Stop", sid="s1"))

    heartbeat = store.compute_heartbeat()
    assert heartbeat["tokens_today"] == 1
    assert heartbeat["entries"] == 0
