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

INPUT="$(cat)"

fallback_log() {
  mkdir -p "$(dirname "$LOG")"
  if [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv -f "$LOG" "$LOG.1"
  fi
  printf '[%s] %s %s daemon-unreachable\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${HOOK_EVENT:-unknown}" "${SESSION_ID:-unknown}" >> "$LOG"
}

if [ -z "$PYTHON_BIN" ]; then
  fallback_log
  exit 0
fi

PAYLOAD="$(
  HOOK_INPUT="$INPUT" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys

try:
    payload = json.loads(os.environ.get("HOOK_INPUT", ""))
    if not isinstance(payload, dict):
        raise ValueError("hook input is not an object")
    payload["type"] = "hook"
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
except Exception:
    sys.exit(1)
PY
)" || {
  fallback_log
  exit 0
}

HOOK_EVENT="$(PAYLOAD="$PAYLOAD" "$PYTHON_BIN" -c 'import json,os; print(json.loads(os.environ["PAYLOAD"]).get("hook_event_name","unknown"))' 2>/dev/null || echo unknown)"
SESSION_ID="$(PAYLOAD="$PAYLOAD" "$PYTHON_BIN" -c 'import json,os; print(json.loads(os.environ["PAYLOAD"]).get("session_id","unknown"))' 2>/dev/null || echo unknown)"

SOCKET_PATH="$SOCKET_PATH" PAYLOAD="$PAYLOAD" "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import os
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(0.2)
try:
    sock.connect(os.environ["SOCKET_PATH"])
    sock.sendall(os.environ["PAYLOAD"].encode("utf-8") + b"\n")
finally:
    sock.close()
PY

if [ "$?" -ne 0 ]; then
  fallback_log
fi

exit 0
