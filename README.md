# Cardputer Buddy

[中文版](README.zh-CN.md)

A physical companion device for [Claude Code](https://claude.ai/code). An M5Stack Cardputer sits next to your keyboard and reacts to your coding activity in real time — a virtual pet that thrives when you code.

## What It Does

A small creature lives on the Cardputer's screen. When Claude Code is actively working, it gets fed. When you complete a task, it gets excited. Leave it idle for too long and it gets hungry.

- **Hunger & Mood** increase while Claude Code is running (+5/+3 every 5 minutes)
- **Task completion** gives a mood and XP boost (+20 mood, +5 XP)
- **Idle decay**: hunger drops by 15 every 6 hours, mood by 10 every 8 hours
- **Evolution**: baby (lvl 0-4) → adult (lvl 5-9, 6 legs) → master (lvl 10+, crowned)
- **Behavior**: low hunger = slow; low mood = frequent blinking; both critical = stops and shows "Feed me!"
- Stats persist across reboots via ESP32 NVS

## Architecture

```
Claude Code hooks ──► Unix socket ──► Daemon ──► BLE ──► Cardputer
```

The Mac-side daemon receives Claude Code hook events (SessionStart, Stop, etc.), aggregates session state, and pushes heartbeats to the Cardputer over BLE using the Nordic UART Service.

## Requirements

- macOS
- Python 3.10+
- [Claude Code](https://claude.ai/code)
- [M5Stack Cardputer or Cardputer-Adv](https://docs.m5stack.com/en/core/Cardputer)

## Setup

### 1. Flash the Cardputer

```bash
# Edit WiFi credentials first
nano build-with-claude/buddy/device/wifi_event.py

# Flash firmware and push apps (requires Claude Code)
# In Claude Code, run: m5-onboard go
```

### 2. Install the daemon

```bash
scripts/install_daemon.sh
```

This creates a venv at `~/.cardputer-daemon/`, installs [bleak](https://github.com/hbldh/bleak), and sets up a LaunchAgent.

### 3. Configure Claude Code hooks

Add the following to `~/.claude/settings.json` (adjust the path):

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "bash '/path/to/cardputer/hook_to_daemon.sh'" }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "bash '/path/to/cardputer/hook_to_daemon.sh'" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "bash '/path/to/cardputer/hook_to_daemon.sh'" }] }],
    "SubagentStop": [{ "hooks": [{ "type": "command", "command": "bash '/path/to/cardputer/hook_to_daemon.sh'" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "bash '/path/to/cardputer/hook_to_daemon.sh'" }] }]
  }
}
```

Restart Claude Code after editing.

## Project Structure

```
├── daemon.py              # Mac daemon entrypoint (asyncio)
├── session_store.py        # Session aggregation, heartbeat generation
├── socket_server.py        # Unix socket server for hook events
├── ble_client.py           # BLE client (bleak) with reconnect
├── hook_to_daemon.sh       # Claude Code hook wrapper
├── scripts/                # Install, uninstall, status
├── tests/                  # Unit tests
└── build-with-claude/      # Device-side code (M5Stack Cardputer)
    └── buddy/device/
        ├── main.py             # MicroPython entrypoint
        ├── buddy_state.py      # Tamagotchi stats + NVS persistence
        ├── buddy_protocol.py   # BLE command handler
        ├── buddy_ble.py        # Nordic UART BLE peripheral
        ├── buddy_ui_cp.py      # Screen rendering
        ├── buddy_sprites.py    # Evolution stage sprites
        └── wifi_event.py       # WiFi auto-connect (edit credentials here)
```

## Debugging

- Daemon log: `~/.cardputer-daemon/daemon.log`
- Mute BLE temporarily: `touch ~/.cardputer-mute`
- Check status: `scripts/cardputer-daemon-status.sh`

## Acknowledgments

| Project | License | Role |
|---------|---------|------|
| [build-with-claude](https://github.com/moremas/build-with-claude) (Anthropic) | Apache 2.0 | Original Cardputer buddy bundle; our Tamagotchi system is built on top |
| [bleak](https://github.com/hbldh/bleak) | MIT | BLE communication from macOS to ESP32 |
| [MicroPython](https://micropython.org/) | MIT | Device runtime (via UIFlow 2.0) |
| [M5Stack UIFlow 2.0](https://uiflow2.m5stack.com/) | MIT | Firmware and hardware abstraction |
| [pyserial](https://github.com/pyserial/pyserial) | BSD-3-Clause | USB serial for device flashing |

## License

Apache 2.0 — see [LICENSE](LICENSE).
