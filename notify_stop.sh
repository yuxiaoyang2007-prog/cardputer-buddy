#!/bin/bash
# Claude Code Stop hook → fire-and-forget BLE notification to Cardputer.
#
# Reads hook JSON from stdin (we ignore it for MVP, just send a generic msg).
# Backgrounds bridge.py so the hook returns immediately and doesn't block the
# end of the assistant's response.
#
# Concurrency: if a previous bridge is still connecting, this one will fail
# to find the device (only one BLE central at a time). We swallow that.

CARDPUTER_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="/tmp/cardputer-hook.log"

# Discard stdin (hook payload) — not used yet
cat >/dev/null

# Allow opt-out by file presence, in case user wants to silence temporarily
if [ -f "$HOME/.cardputer-mute" ]; then
  exit 0
fi

# Fire bridge in background; release this process immediately
(
  cd "$CARDPUTER_DIR" || exit 0
  /opt/homebrew/bin/python3 "$CARDPUTER_DIR/bridge.py" \
    --msg "Claude done ✦" \
    --listen 8 \
    --timeout 4 \
    >>"$LOG" 2>&1
  echo "--- end $(date '+%H:%M:%S') ---" >>"$LOG"
) </dev/null >/dev/null 2>&1 &

disown
exit 0
