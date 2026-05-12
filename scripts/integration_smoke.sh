#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
SOCKET_PATH="${CARDPUTER_DAEMON_SOCKET:-${HOME}/.cardputer-daemon/control.sock}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="/opt/homebrew/bin/python3"
fi

CARDPUTER_DAEMON_DEBUG=1 CARDPUTER_DAEMON_STDERR=1 "$PYTHON_BIN" "$ROOT/daemon.py" &
DAEMON_PID="$!"
echo "Started local smoke daemon PID: ${DAEMON_PID}"

cleanup() {
  if kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "Stopping local smoke daemon PID: ${DAEMON_PID}"
    kill -TERM "$DAEMON_PID"
    wait "$DAEMON_PID" || true
  fi
}
trap cleanup EXIT

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [ -S "$SOCKET_PATH" ]; then
    break
  fi
  sleep 0.5
done

for event in SessionStart UserPromptSubmit Stop SubagentStop SessionEnd; do
  printf '{"hook_event_name":"%s","session_id":"smoke","cwd":"%s","transcript_path":"/tmp/smoke.jsonl"}\n' "$event" "$ROOT" \
    | CARDPUTER_DAEMON_SOCKET="$SOCKET_PATH" "$ROOT/hook_to_daemon.sh"
done

CARDPUTER_DAEMON_SOCKET="$SOCKET_PATH" "$PYTHON_BIN" - <<'PY'
import json
import os
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(1.0)
sock.connect(os.environ.get("CARDPUTER_DAEMON_SOCKET", os.path.expanduser("~/.cardputer-daemon/control.sock")))
sock.sendall(b'{"type":"status"}\n')
print(json.dumps(json.loads(sock.recv(65536).decode("utf-8")), indent=2))
sock.close()
PY
