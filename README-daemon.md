# Cardputer Daemon

macOS LaunchAgent daemon for keeping one long-lived BLE connection to the M5 Cardputer and aggregating Claude Code hook events from concurrent sessions.

## Files

- `daemon.py`: asyncio entrypoint, flock, logging, TTL ticker, event consumer.
- `session_store.py`: idempotent session upsert, counters, TTL prune, heartbeat snapshot.
- `socket_server.py`: Unix socket JSON line protocol at `~/.cardputer-daemon/control.sock`.
- `ble_client.py`: bleak client, reconnect backoff, dirty heartbeat resend.
- `hook_to_daemon.sh`: Claude Code hook wrapper; stdin JSON to daemon socket, fallback log on failure.
- `scripts/cardputer-daemon-status.sh`: status JSON request.
- `scripts/install_daemon.sh`: venv, plist render, optional LaunchAgent bootstrap after confirmation.
- `scripts/uninstall_daemon.sh`: confirmed LaunchAgent removal.

## Install

```bash
cd "/Users/xiaoyangyu/Claude Code/cardputer"
scripts/install_daemon.sh
```

The installer creates `~/.cardputer-daemon/`, installs `bleak` into `~/.cardputer-daemon/venv`, renders `~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`, then asks before running:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist
```

If you answer no, review the plist and run the command manually later.

## Status

```bash
cd "/Users/xiaoyangyu/Claude Code/cardputer"
scripts/cardputer-daemon-status.sh
```

The reply includes `ble_state`, `sessions`, `tokens_today`, `entries_today`, `last_heartbeat`, and uptime.

## Uninstall

```bash
cd "/Users/xiaoyangyu/Claude Code/cardputer"
scripts/uninstall_daemon.sh
```

The script asks before calling `launchctl bootout` and deleting the plist. It keeps `~/.cardputer-daemon/` so logs and the venv remain available for inspection.

## Claude Code Hooks

Do not edit `~/.claude/settings.json` blindly. Read the hooks section first, generate a diff, then apply by hand and restart Claude Code with `/exit`.

Example command target:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"
          }
        ]
      }
    ]
  }
}
```

Settings hook changes are not hot reloaded. After editing, run `/exit` and start Claude Code again.

## Slice 0 SessionEnd Check

This repo does not automate the SessionEnd verification because it modifies `~/.claude/settings.json`.

Manual flow:

1. Save current hooks: `jq '.hooks // {}' ~/.claude/settings.json > /tmp/hooks-before.json`.
2. Generate a candidate settings file that adds a temporary SessionEnd hook writing to `/tmp/cc-sessionend-test.log`.
3. Show a sorted JSON diff between current settings and the candidate.
4. Apply only after review.
5. Validate syntax with `jq . ~/.claude/settings.json`.
6. Restart Claude Code with `/exit`.
7. Test start, stop, clear, and resume cases; inspect `/tmp/cc-sessionend-test.log`.
8. Restore settings using the same diff-first flow and validate with `jq .`.
9. Restart Claude Code again.

TTL prune remains necessary even if SessionEnd fires, because hook delivery can still be missed.

## Debugging

- Logs: `~/.cardputer-daemon/daemon.log`
- Fallback hook log: `~/.cardputer-daemon/hook-fallback.log`
- Mute BLE writes while keeping internal state: `touch ~/.cardputer-mute`
- Unmute: `rm ~/.cardputer-mute`

When the daemon is running it owns the BLE connection. Running `bridge.py` at the same time is expected to fail or disconnect because the Cardputer BLE peripheral allows only one host connection.
