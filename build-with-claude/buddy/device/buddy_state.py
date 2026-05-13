"""Persistent state for the buddy: name, owner, lifetime counters.

Kept in ESP32 NVS under a dedicated "buddy" namespace so that a
device reflash of UIFlow doesn't clobber settings — the firmware
partition and NVS partition are separate.

Counters tracked (names chosen to match the desktop `stats` ack shape):
  appr  total permission approvals over device lifetime
  deny  total denials
  vel   exponential moving average of permissions/minute
  nap   number of idle periods (no activity > 5 min) — vanity metric
  lvl   derived level = int(sqrt(appr + deny)), a toy tamagotchi gauge

vel/nap/lvl are best-effort — the desktop uses them to render a
personality badge, so mild imprecision is fine. What matters is
monotonicity of appr/deny so the user's approval history is stable
across reboots.
"""

import time


try:
    import esp32

    _NVS = esp32.NVS("buddy")
except ImportError:
    _NVS = None  # dev machine stub


def _get_str(key: str, default: str = "") -> str:
    if _NVS is None:
        return default
    try:
        buf = bytearray(128)
        n = _NVS.get_blob(key, buf)
        return bytes(buf[:n]).decode("utf-8", errors="replace")
    except Exception:
        return default


def _set_str(key: str, value: str) -> None:
    if _NVS is None:
        return
    _NVS.set_blob(key, value.encode("utf-8"))
    _NVS.commit()


def _get_int(key: str, default: int = 0) -> int:
    if _NVS is None:
        return default
    try:
        return _NVS.get_i32(key)
    except Exception:
        return default


def _set_int(key: str, value: int) -> None:
    if _NVS is None:
        return
    _NVS.set_i32(key, value)
    _NVS.commit()


def _erase(key: str) -> None:
    if _NVS is None:
        return
    try:
        _NVS.erase_key(key)
    except Exception:
        pass


class BuddyState:
    """In-memory state mirror, write-through to NVS on changes."""

    _FEED_COOLDOWN_MS = 5 * 60 * 1000
    _HUNGER_DECAY_INTERVAL_MS = 6 * 3600 * 1000
    _MOOD_DECAY_INTERVAL_MS = 8 * 3600 * 1000
    _NVS_WRITE_THROTTLE_MS = 10 * 60 * 1000

    def __init__(self):
        self.name = _get_str("name", "Buddy")
        self.owner = _get_str("owner", "")
        self.appr = _get_int("appr", 0)
        self.deny = _get_int("deny", 0)
        self.hunger = min(100, max(0, _get_int("thgr", 50)))
        self.mood = min(100, max(0, _get_int("tmod", 50)))
        self.xp = max(0, _get_int("txp", 0))
        self._vel = 0.0  # per-minute EWMA, not persisted across reboots
        self._nap_count = _get_int("nap", 0)
        now = time.ticks_ms()
        self._last_action_ms = now
        self._nap_window_ms = 5 * 60 * 1000
        self._last_feed_ticks = now
        self._last_decay_ticks = now
        self._last_nvs_write_ticks = now

    def set_name(self, name: str) -> None:
        self.name = name[:32]
        _set_str("name", self.name)

    def set_owner(self, owner: str) -> None:
        self.owner = owner[:64]
        _set_str("owner", self.owner)

    def record_decision(self, decision: str) -> None:
        """Called on a permission decision (once|deny)."""
        now = time.ticks_ms()
        if decision == "once":
            self.appr += 1
            _set_int("appr", self.appr)
        elif decision == "deny":
            self.deny += 1
            _set_int("deny", self.deny)
        else:
            return

        dt_s = max(0.5, time.ticks_diff(now, self._last_action_ms) / 1000.0)
        inst_per_min = 60.0 / dt_s
        # Smoothing factor 0.3 — fast enough to feel live, slow enough
        # that a single button-mash doesn't pin vel at some huge value.
        self._vel = self._vel * 0.7 + inst_per_min * 0.3
        self._last_action_ms = now

    def tick_nap(self) -> None:
        """Call periodically; counts stretches of no activity."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_action_ms) > self._nap_window_ms:
            self._nap_count += 1
            _set_int("nap", self._nap_count)
            self._last_action_ms = now  # reset window so we don't double-count

    def feed(self, coding_active: bool) -> None:
        """coding_active=True and >=5 min since last feed: hunger +10, mood +5."""
        if not coding_active:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_feed_ticks) < self._FEED_COOLDOWN_MS:
            return
        self._last_feed_ticks = now
        self.hunger = min(100, self.hunger + 5)
        self.mood = min(100, self.mood + 3)
        self._maybe_save_tama()

    def feed_done(self) -> None:
        """notif.t='done': mood +20, xp +5. Not limited by feed cooldown."""
        self.mood = min(100, self.mood + 20)
        self.xp += 5
        self._save_tama()

    def tick_decay(self) -> None:
        """Apply elapsed-time decay for the current boot session."""
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_decay_ticks)
        hunger_decay = (elapsed * 15) // self._HUNGER_DECAY_INTERVAL_MS
        mood_decay = (elapsed * 10) // self._MOOD_DECAY_INTERVAL_MS
        if hunger_decay > 0 or mood_decay > 0:
            self.hunger = max(0, self.hunger - hunger_decay)
            self.mood = max(0, self.mood - mood_decay)
            self._last_decay_ticks = now
            self._maybe_save_tama()

    def evolution_stage(self) -> int:
        """Return 1/2/3 based on triangular XP level."""
        lvl = self._tama_level()
        if lvl >= 10:
            return 3
        if lvl >= 5:
            return 2
        return 1

    def tama_stats(self) -> dict:
        """Snapshot for UI rendering."""
        lvl = self._tama_level()
        return {
            "hunger": self.hunger,
            "mood": self.mood,
            "xp": self.xp,
            "stage": self.evolution_stage(),
            "lvl": lvl,
        }

    def _tama_level(self) -> int:
        lvl = 0
        t = self.xp
        while t > 0:
            lvl += 1
            t -= lvl
        return lvl

    def _maybe_save_tama(self) -> None:
        """Throttle NVS writes to at most once every 10 minutes."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_nvs_write_ticks) < self._NVS_WRITE_THROTTLE_MS:
            return
        self._save_tama()

    def _save_tama(self) -> None:
        """Batch-write Tamagotchi values to NVS with a single commit."""
        if _NVS is None:
            return
        _NVS.set_i32("thgr", self.hunger)
        _NVS.set_i32("tmod", self.mood)
        _NVS.set_i32("txp", self.xp)
        _NVS.commit()
        self._last_nvs_write_ticks = time.ticks_ms()

    def stats(self) -> dict:
        total = self.appr + self.deny
        # Triangular progression: each level costs one more action
        # than the last. Hit points: level 1 at 1 action, level 10
        # at 55 (=1+2+...+10), level 100 at 5050. The previous
        # comment mis-described this as a sqrt curve (level 10 at
        # 100, level 100 at 10000); the loop below is and always
        # was triangular — only the comment was wrong.
        lvl = 0
        t = total
        while t > 0:
            lvl += 1
            t -= lvl
        return {
            "appr": self.appr,
            "deny": self.deny,
            "vel": round(self._vel, 2),
            "nap": self._nap_count,
            "lvl": lvl,
        }

    def reset_all(self) -> None:
        """Called on unpair. Wipes name/owner/counters but not firmware."""
        self.name = "Buddy"
        self.owner = ""
        self.appr = 0
        self.deny = 0
        self.hunger = 50
        self.mood = 50
        self.xp = 0
        self._vel = 0.0
        self._nap_count = 0
        now = time.ticks_ms()
        self._last_feed_ticks = now
        self._last_decay_ticks = now
        self._last_nvs_write_ticks = now
        for k in ("name", "owner", "appr", "deny", "nap", "thgr", "tmod", "txp"):
            _erase(k)
        if _NVS is not None:
            _NVS.commit()
