# Buddy UI for 240x135 Cardputer-Adv LCD. Uses drawString + textWidth.

import time
import M5

# Optional burst animation — same source the launcher uses (waiting.webp,
# 16 frames, 72x72, orange 0xDA7757). When unavailable, idle screen stays
# text-only without breaking.
try:
    import burst_frames as _burst
except ImportError as _e:
    print("buddy_ui_cp: burst_frames not available:", _e)
    _burst = None

import buddy_sprites as _sprites

# Anthropic palette, inlined — byte-for-byte matches ui_theme.py.
ORANGE = 0xCC785C
CREAM = 0xF0EEE6
DARK = 0x1F1F1F
BLACK = 0x000000
WHITE = 0xFFFFFF
GRAY_DIM = 0x333333
GRAY_MID = 0x777777
GREEN = 0x00FF00
CYAN = 0x00FFFF
YELLOW = 0xFFFF00
RED = 0xFF0000

_LCD = M5.Lcd

_W = 240
_H = 135

# Burst starburst on the right (rendered at 2/3 scale from the 72x72
# source frames); Clawd runs across the bottom at ~1.3x the original.
_BURST_W = 48
_BURST_H = 48
_BURST_X = 180
_BURST_Y = 32
_TEXT_MAX_W = _BURST_X - 12                          # 168
# Running Clawd: max stage is 30 wide x 22 tall, bouncing left-right at y=91.
_RUN_W = 30
_RUN_H = 22
_RUN_Y = 91
_RUN_MIN_X = 2
_RUN_MAX_X = _W - _RUN_W - 2                        # 208
_RUN_SPEED = 2
_BLINK_CYCLE = 45
_BLINK_DUR = 3


def _right(y: int, pad: int, text: str) -> int:
    """Cursor X so `text` ends `pad` px from the right edge."""
    return _W - pad - _LCD.textWidth(text)


def _center(text: str) -> int:
    """Cursor X to horizontally center `text` in the viewport."""
    return (_W - _LCD.textWidth(text)) // 2


class BuddyUI:

    def __init__(self):
        self._last = {}
        self._passkey = None
        # Unpair confirmation overlay: True while the host has asked
        # us to unpair and we're waiting for an on-device Y/N press.
        # See the threat model in buddy_ble.py — the BLE link is
        # unauthenticated, so destructive commands need an in-person
        # confirmation that an in-range BLE attacker can't fake.
        self._unpair_prompt = False
        self._connection_state = "advertising"
        self._prompt = None
        self._identity_name = "Buddy"
        self._identity_owner = ""
        self._clawd_x = _RUN_MIN_X
        self._clawd_dir = 1
        self._mood = "sleepy"
        self._celebrate_ms = 0
        self._tama_stats = None
        _LCD.fillScreen(BLACK)
        # setFont is sticky across setTextSize calls, so we pick
        # DejaVu9 once at init. Wrapped in try/except so a future
        # UIFlow build that drops the font still loads us (falls back
        # to the default at an uglier size).
        try:
            _LCD.setFont(_LCD.FONTS.DejaVu9)
        except Exception as e:
            print("buddy_ui_cp: setFont fallback:", e)
        # No setRotation — Cardputer-Adv boots in landscape already.
        self._redraw_chrome()

    # ---- public setters (shape matches Basic's BuddyUI)

    def set_connection(self, state: str):
        if state == self._connection_state:
            return
        self._connection_state = state
        self._draw_header()
        if state in ("advertising", "disconnected"):
            self._prompt = None
            self._last = {}
        self._draw_main()
        self.restore_button_hints()

    def show_passkey(self, pk: int):
        self._passkey = pk
        self._draw_passkey_overlay()
        self.restore_button_hints()

    def clear_passkey(self):
        if self._passkey is None:
            return
        self._passkey = None
        self._draw_main()

    def show_unpair_prompt(self):
        self._unpair_prompt = True
        self._draw_unpair_overlay()
        self.restore_button_hints()

    def clear_unpair_prompt(self):
        if not self._unpair_prompt:
            return
        self._unpair_prompt = False
        self._draw_main()
        self.restore_button_hints()

    def update_heartbeat(self, hb: dict, tama_stats: dict = None):
        prev_pending = bool(self._prompt)
        self._last = hb
        if tama_stats is not None:
            self._tama_stats = tama_stats
        self._prompt = hb.get("prompt")
        notif = hb.get("notif")
        running = hb.get("running", 0)
        if notif and notif.get("t") == "done":
            self._mood = "celebrate"
            self._celebrate_ms = time.ticks_ms()
        elif self._mood != "celebrate":
            self._mood = "busy" if running > 0 else "sleepy"
        self._draw_main()
        if bool(self._prompt) != prev_pending:
            self.restore_button_hints()

    def update_identity(self, name: str, owner: str):
        self._identity_name = name or "Buddy"
        self._identity_owner = owner or ""
        if self._connection_state not in ("advertising", "disconnected"):
            self._draw_identity()

    def update_footer(self, stats: dict, battery: dict):
        # Stats footer only appears during the connected layout.
        if self._connection_state not in ("advertising", "disconnected"):
            self._draw_footer(stats, battery)

    def flash_decision(self, decision: str):
        color = GREEN if decision == "once" else RED
        self.flash_toast(decision.upper() + " sent", color)

    def flash_toast(self, text: str, color: int = CYAN):
        """Overwrite the hint strip with a one-line colored status."""
        _LCD.fillRect(0, 112, _W, _H - 112, color)
        _LCD.setTextColor(WHITE, color)
        _LCD.setTextSize(1)
        # Clip to whatever fits on the strip; in practice callers
        # keep text short.
        t = text
        while _LCD.textWidth(t) > _W - 12 and len(t) > 1:
            t = t[:-1]
        _LCD.drawString(t, 6, 117)

    def restore_button_hints(self):
        # Thin orange hairline above the strip + DARK fill.
        _LCD.fillRect(0, 111, _W, 1, ORANGE)
        _LCD.fillRect(0, 112, _W, _H - 112, DARK)
        _LCD.setTextColor(CREAM, DARK)
        _LCD.setTextSize(1)
        if self._unpair_prompt:
            # Only Y and N during a destructive-action confirmation;
            # showing Q here invites a thumb-fumble exit that leaves
            # the host hanging on a pending ack.
            _LCD.drawString("Y confirm", 8, 117)
            n = "N cancel"
            _LCD.drawString(n, _right(117, 8, n), 117)
            return
        if self._passkey is not None:
            # During pairing only Q makes sense — Y and N don't
            # actually do anything until the encrypted state fires.
            label = "Q = Exit"
            _LCD.drawString(label, _center(label), 117)
            return
        # 3-column layout. Measured widths on DejaVu9: 38/39/34 px.
        # Left-aligned columns at x=8/96/right-aligned-8 give the
        # eye a clear "approve / deny / back" reading order.
        _LCD.drawString("Y once", 8, 117)
        _LCD.drawString("N deny", 96, 117)
        q = "Q exit"
        _LCD.drawString(q, _right(117, 8, q), 117)

    def is_idle(self) -> bool:
        return (
            self._connection_state in ("advertising", "disconnected")
            and self._passkey is None
            and self._prompt is None
            and not self._unpair_prompt
        )

    def tick_burst(self, frame, last_tick):
        if self._passkey is not None or self._unpair_prompt:
            return frame, last_tick
        now = time.ticks_ms()
        interval = _burst.FRAME_MS if _burst is not None else 80
        if last_tick and time.ticks_diff(now, last_tick) < interval:
            return frame, last_tick
        # Burst starburst on the right, scaled 2/3 from 72x72 source
        _LCD.fillRect(_BURST_X, _BURST_Y, _BURST_W, _BURST_H, BLACK)
        _LCD.fillRect(_BURST_X, 82, _W - _BURST_X, 12, BLACK)
        if _burst is not None:
            data = _burst.FRAMES[frame % len(_burst.FRAMES)]
            color = _burst.COLOR
            i = 0
            n = len(data)
            while i < n:
                sy = data[i] * 2 // 3
                sx = data[i + 1] * 2 // 3
                sl = data[i + 2] * 2 // 3 or 1
                _LCD.fillRect(_BURST_X + sx, _BURST_Y + sy, sl, 1, color)
                i += 3
        # Expire celebration after 5 seconds
        if self._mood == "celebrate" and self._celebrate_ms:
            if time.ticks_diff(now, self._celebrate_ms) > 5000:
                running = self._last.get("running", 0)
                self._mood = "busy" if running > 0 else "sleepy"
                self._celebrate_ms = 0
        stats = self._tama_stats or {}
        stage = stats.get("stage", 1)
        hunger = stats.get("hunger", 50)
        tama_mood = stats.get("mood", 50)
        if stage >= 3:
            draw_clawd = _sprites.draw_master
            sprite_h = 22
            sprite_y = _RUN_Y - 2
        elif stage == 2:
            draw_clawd = _sprites.draw_adult
            sprite_h = 20
            sprite_y = _RUN_Y
        else:
            draw_clawd = _sprites.draw_baby
            sprite_h = 20
            sprite_y = _RUN_Y
        blink_cycle = _BLINK_CYCLE
        if tama_mood <= 20:
            blink_cycle = max(8, _BLINK_CYCLE // 2)
        mood = self._mood
        sparkles = False
        if mood == "celebrate":
            jump = 3 if (frame % 8) < 4 else 0
            cy = sprite_y - jump
            blink = False
            walk = (frame // 2) % 2
            speed = 1
            sparkles = (frame % 4) < 2
        elif mood == "busy":
            cy = sprite_y
            blink = (frame % blink_cycle) >= (blink_cycle - _BLINK_DUR)
            walk = (frame // 3) % 2
            speed = 3
        else:
            # Sleepy: slow, eyes closed 30% of the time
            cy = sprite_y
            sleepy_cycle = 10 if tama_mood <= 20 else 20
            blink = (frame % sleepy_cycle) >= (sleepy_cycle * 7 // 10)
            walk = (frame // 6) % 2
            speed = 1
        if hunger <= 10 and tama_mood <= 10:
            speed = 0
            walk = 0
            blink = True
        clear_y = min(cy - 4 if sparkles else cy, _RUN_Y)
        clear_y = max(80, clear_y)
        clear_h = max(1, 111 - clear_y)
        _LCD.fillRect(0, clear_y, _W, clear_h, BLACK)
        _sprites.draw_environment(stage, _RUN_Y + min(sprite_h, 20), _W)
        draw_clawd(self._clawd_x, cy, blink, walk)
        if sparkles:
            _LCD.fillRect(self._clawd_x + 9, cy - 3, 2, 2, YELLOW)
            _LCD.fillRect(self._clawd_x + 1, cy - 2, 1, 1, YELLOW)
            _LCD.fillRect(self._clawd_x + 17, cy - 2, 1, 1, YELLOW)
        if speed == 0 and self._prompt is None:
            _LCD.setTextSize(1)
            _LCD.setTextColor(RED, BLACK)
            _LCD.drawString("Feed me", _BURST_X + 2, 84)
        move_speed = speed
        if hunger <= 20 and move_speed > 0:
            if move_speed == 1:
                move_speed = 0 if (frame % 2) else 1
            else:
                move_speed = max(1, move_speed // 2)
        self._clawd_x += move_speed * self._clawd_dir
        if self._clawd_x >= _RUN_MAX_X:
            self._clawd_x = _RUN_MAX_X
            self._clawd_dir = -1
        elif self._clawd_x <= _RUN_MIN_X:
            self._clawd_x = _RUN_MIN_X
            self._clawd_dir = 1
        return frame + 1, now

    # ---- drawing primitives

    def _draw_header(self):
        _LCD.fillRect(0, 0, _W, 20, DARK)
        _LCD.fillRect(0, 20, _W, 1, ORANGE)
        _LCD.setTextSize(1)
        _LCD.setTextColor(ORANGE, DARK)
        _LCD.drawString("Claude Buddy", 6, 5)
        icon, color = self._connection_icon()
        _LCD.setTextColor(color, DARK)
        _LCD.drawString(icon, _right(5, 6, icon), 5)

    def _connection_icon(self):
        s = self._connection_state
        if s == "encrypted":
            return ("LINKED", GREEN)
        if s == "connected":
            return ("PAIR..", YELLOW)
        if s == "disconnected":
            return ("OFF", RED)
        return ("ADV", CYAN)

    def _draw_identity(self):
        name = (self._identity_name or "Buddy")[:22]
        owner = self._identity_owner or ""
        _LCD.fillRect(0, 24, _W, 14, BLACK)
        _LCD.setTextSize(1)
        _LCD.setTextColor(ORANGE, BLACK)
        _LCD.drawString(name, 6, 26)
        if owner:
            _LCD.setTextColor(GRAY_MID, BLACK)
            # Place owner text just after name with an 8 px gutter.
            x = 6 + _LCD.textWidth(name) + 8
            suffix = "<- " + owner
            # Clip the owner suffix to whatever fits before the right
            # margin (the status icon is in the header, not here).
            while x + _LCD.textWidth(suffix) > _TEXT_MAX_W and len(suffix) > 1:
                suffix = suffix[:-1]
            _LCD.drawString(suffix, x, 26)

    def _draw_main(self):
        if self._unpair_prompt:
            _LCD.fillRect(0, 21, _W, 90, BLACK)
            self._draw_unpair_overlay()
            return
        if self._passkey is not None:
            _LCD.fillRect(0, 21, _W, 90, BLACK)
            self._draw_passkey_overlay()
            return
        _LCD.fillRect(0, 21, _BURST_X, _RUN_Y - 21, BLACK)
        if self._connection_state in ("advertising", "disconnected"):
            self._draw_idle_main()
            return
        self._draw_connected_main()

    def _draw_idle_main(self):
        _LCD.setTextSize(1)
        _LCD.setTextColor(CREAM, BLACK)
        _LCD.drawString("Waiting for", 6, 40)
        _LCD.drawString("Claude Code...", 6, 56)

    def _draw_connected_main(self):
        self._draw_identity()
        hb = self._last
        _LCD.setTextSize(1)
        usage = hb.get("usage") or {}
        if usage:
            self._draw_usage_line(usage, 6, 42)
        else:
            running = hb.get("running", 0)
            waiting = hb.get("waiting", 0)
            total = hb.get("total", 0)
            q_color = GREEN if running > 0 else GRAY_MID
            _LCD.setTextColor(q_color, BLACK)
            queue = "Q: {}run {}wait {}tot".format(running, waiting, total)
            while _LCD.textWidth(queue) > _TEXT_MAX_W and len(queue) > 1:
                queue = queue[:-1]
            _LCD.drawString(queue, 6, 42)
        events = hb.get("tokens_today", 0)
        _LCD.setTextColor(CYAN, BLACK)
        ev_line = "Today: {} hooks".format(events)
        while _LCD.textWidth(ev_line) > _TEXT_MAX_W and len(ev_line) > 1:
            ev_line = ev_line[:-1]
        _LCD.drawString(ev_line, 6, 58)
        if self._prompt:
            self._draw_prompt_box(self._prompt)
        elif self._tama_stats:
            self._draw_tama_line(self._tama_stats)
        else:
            msg = hb.get("msg", "")
            if msg:
                if self._mood == "celebrate":
                    msg_color = GREEN
                elif self._mood == "busy":
                    msg_color = ORANGE
                else:
                    msg_color = GRAY_MID
                _LCD.setTextColor(msg_color, BLACK)
                while _LCD.textWidth(msg) > _TEXT_MAX_W and len(msg) > 1:
                    msg = msg[:-1]
                _LCD.drawString(msg, 6, 74)

    def _draw_usage_line(self, usage: dict, x: int, y: int):
        """Render: 5h[####.]45% 7d[#....]12% — yellow/red bars when high."""
        five = usage.get("5h")
        week = usage.get("7d")
        _LCD.setTextSize(1)
        cur_x = x
        for label, pct in (("5h", five), ("7d", week)):
            if pct is None:
                continue
            pct = max(0, min(100, int(pct)))
            _LCD.setTextColor(GRAY_MID, BLACK)
            _LCD.drawString(label, cur_x, y)
            cur_x += _LCD.textWidth(label) + 1
            bar_x, bar_y, bar_w, bar_h = cur_x, y + 1, 30, 7
            _LCD.drawRect(bar_x, bar_y, bar_w, bar_h, GRAY_MID)
            fill_w = (bar_w - 2) * pct // 100
            if pct >= 90:
                color = RED
            elif pct >= 70:
                color = YELLOW
            else:
                color = GREEN
            if fill_w > 0:
                _LCD.fillRect(bar_x + 1, bar_y + 1, fill_w, bar_h - 2, color)
            cur_x += bar_w + 2
            pct_text = "{}%".format(pct)
            _LCD.setTextColor(CREAM, BLACK)
            _LCD.drawString(pct_text, cur_x, y)
            cur_x += _LCD.textWidth(pct_text) + 6

    def _draw_tama_line(self, stats: dict):
        hunger = stats.get("hunger", 50)
        mood = stats.get("mood", 50)
        lvl = stats.get("lvl", 0)
        stage = stats.get("stage", 1)
        x = 6
        y = 74
        _LCD.setTextSize(1)
        _LCD.setTextColor(CREAM, BLACK)
        h_text = "H{}".format(hunger)
        _LCD.drawString(h_text, x, y)
        x += _LCD.textWidth(h_text) + 2
        h_color = GREEN if hunger > 30 else RED
        _LCD.fillRect(x, y + 3, 4, 4, h_color)
        x += 8
        m_text = "M{}".format(mood)
        _LCD.setTextColor(CREAM, BLACK)
        _LCD.drawString(m_text, x, y)
        x += _LCD.textWidth(m_text) + 2
        m_color = ORANGE if mood > 30 else RED
        _LCD.fillRect(x, y + 3, 4, 4, m_color)
        x += 8
        level_text = "Lv{}{}".format(lvl, "*" * stage)
        while x + _LCD.textWidth(level_text) > _TEXT_MAX_W and len(level_text) > 1:
            level_text = level_text[:-1]
        _LCD.setTextColor(CYAN, BLACK)
        _LCD.drawString(level_text, x, y)

    def _draw_prompt_box(self, prompt: dict):
        _LCD.drawRect(3, 74, _TEXT_MAX_W, 16, ORANGE)
        _LCD.setTextSize(1)
        _LCD.setTextColor(ORANGE, BLACK)
        tool_line = "PERM: " + prompt.get("tool", "?")
        while _LCD.textWidth(tool_line) > _TEXT_MAX_W - 8 and len(tool_line) > 1:
            tool_line = tool_line[:-1]
        _LCD.drawString(tool_line, 7, 76)
        hint = prompt.get("hint", "")
        _LCD.setTextColor(CREAM, BLACK)
        while _LCD.textWidth(hint) > _TEXT_MAX_W - 8 and len(hint) > 1:
            hint = hint[:-1]
        _LCD.drawString(hint, 7, 84)

    def _draw_unpair_overlay(self):
        if not self._unpair_prompt:
            return
        _LCD.fillRect(0, 21, _W, 90, BLACK)
        _LCD.setTextSize(1)
        _LCD.setTextColor(RED, BLACK)
        # Two-line attention header so the destructive nature is clear
        # at a glance — this is the only path that wipes user state.
        _LCD.drawString("UNPAIR REQUEST", 6, 28)
        _LCD.setTextColor(CREAM, BLACK)
        _LCD.drawString("from connected host.", 6, 46)
        _LCD.drawString("Wipes name, owner, stats", 6, 64)
        _LCD.drawString("and disconnects.", 6, 78)
        _LCD.setTextColor(GRAY_MID, BLACK)
        _LCD.drawString("Y confirm   N cancel", 6, 96)

    def _draw_passkey_overlay(self):
        if self._passkey is None:
            return
        _LCD.fillRect(0, 21, _W, 90, BLACK)
        _LCD.setTextSize(1)
        _LCD.setTextColor(ORANGE, BLACK)
        _LCD.drawString("Pairing passkey:", 6, 28)
        # Size 4 passkey on DejaVu9 = 40 px tall, ~6 digits wide.
        # Centered with textWidth so size-4 doesn't throw off the math.
        pk_str = "{:06d}".format(self._passkey)
        _LCD.setTextColor(CREAM, BLACK)
        _LCD.setTextSize(4)
        pk_w = _LCD.textWidth(pk_str)
        _LCD.drawString(pk_str, (_W - pk_w) // 2, 44)
        _LCD.setTextSize(1)
        _LCD.setTextColor(GRAY_MID, BLACK)
        _LCD.drawString("type it into Claude", 6, 96)

    def _draw_footer(self, stats: dict, battery: dict):
        pass

    def _redraw_chrome(self):
        _LCD.fillScreen(BLACK)
        self._draw_header()
        self._draw_main()
        self.restore_button_hints()
