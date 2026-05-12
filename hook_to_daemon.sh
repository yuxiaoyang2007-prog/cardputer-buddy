#!/usr/bin/env bash
set -u

RUNTIME_DIR="${HOME}/.cardputer-daemon"
SOCKET_PATH="${CARDPUTER_DAEMON_SOCKET:-${RUNTIME_DIR}/control.sock}"
LOG="${RUNTIME_DIR}/hook-fallback.log"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR" 2>/dev/null || true

fallback_log() {
  local hook_event="${1:-unknown}"
  local session_id="${2:-unknown}"
  mkdir -p "$(dirname "$LOG")"
  if [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv -f "$LOG" "$LOG.1"
  fi
  printf '[%s] %s %s daemon-unreachable\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$hook_event" "$session_id" >> "$LOG"
}

if [ -z "$PYTHON_BIN" ]; then
  fallback_log
  exit 0
fi

PY_OUTPUT="$(
"$PYTHON_BIN" -c '
import json
import socket
import sys

socket_path = sys.argv[1]
hook_event = "unknown"
session_id = "unknown"

try:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("hook input is not an object")
    hook_event = str(payload.get("hook_event_name") or "unknown")
    session_id = str(payload.get("session_id") or "unknown")
    payload["type"] = "hook"
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        sock.connect(socket_path)
        sock.sendall(line)
    finally:
        sock.close()
except Exception:
    print(f"{hook_event}\t{session_id}")
    sys.exit(1)
' "$SOCKET_PATH" 2>/dev/null
)"
PY_STATUS="$?"

if [ "$PY_STATUS" -ne 0 ]; then
  IFS=$'\t' read -r hook_event session_id <<< "$PY_OUTPUT"
  fallback_log "${hook_event:-unknown}" "${session_id:-unknown}"
fi

exit 0
