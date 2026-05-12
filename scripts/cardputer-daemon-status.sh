#!/usr/bin/env bash
set -euo pipefail

SOCKET_PATH="${CARDPUTER_DAEMON_SOCKET:-${HOME}/.cardputer-daemon/control.sock}"

if [ ! -S "$SOCKET_PATH" ]; then
  echo "socket not found: ${SOCKET_PATH}" >&2
  exit 1
fi

REPLY="$((printf '{"type":"status"}\n'; sleep 0.1) | nc -U "$SOCKET_PATH")"
if command -v jq >/dev/null 2>&1; then
  printf '%s\n' "$REPLY" | jq .
else
  printf '%s\n' "$REPLY"
fi
