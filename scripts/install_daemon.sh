#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${HOME}/.cardputer-daemon"
PLIST_TEMPLATE="${ROOT}/cn.joulian.cardputer-daemon.plist.template"
PLIST_PATH="${HOME}/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist"
PYTHON_BASE="${PYTHON_BASE:-/opt/homebrew/bin/python3}"

if [ ! -x "$PYTHON_BASE" ]; then
  PYTHON_BASE="$(command -v python3 || true)"
fi

if [ -z "$PYTHON_BASE" ]; then
  echo "python3 not found" >&2
  exit 1
fi

echo "Using Python: ${PYTHON_BASE}"
echo "Runtime directory: ${RUNTIME_DIR}"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

"$PYTHON_BASE" -m venv "${RUNTIME_DIR}/venv"
"${RUNTIME_DIR}/venv/bin/python" -m pip install --upgrade pip
"${RUNTIME_DIR}/venv/bin/pip" install -r "${ROOT}/requirements.txt"
"${RUNTIME_DIR}/venv/bin/python" -c "import bleak; import importlib.metadata as m; print('bleak', m.version('bleak'))"

mkdir -p "$(dirname "$PLIST_PATH")"
HOME_VALUE="$HOME" REPO_ROOT="$ROOT" PLIST_TEMPLATE="$PLIST_TEMPLATE" PLIST_PATH="$PLIST_PATH" "${RUNTIME_DIR}/venv/bin/python" - <<'PY'
import os
from pathlib import Path

template = Path(os.environ["PLIST_TEMPLATE"]).read_text(encoding="utf-8")
rendered = (
    template
    .replace("__HOME__", os.environ["HOME_VALUE"])
    .replace("__REPO_ROOT__", os.environ["REPO_ROOT"])
)
Path(os.environ["PLIST_PATH"]).write_text(rendered, encoding="utf-8")
PY

echo "Rendered plist: ${PLIST_PATH}"
echo "Next operation would register LaunchAgent:"
echo "launchctl bootstrap gui/$(id -u) ${PLIST_PATH}"
read -r -p "Run launchctl bootstrap now? [y/N] " answer
case "$answer" in
  y|Y|yes|YES)
    launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
    launchctl print "gui/$(id -u)/cn.joulian.cardputer-daemon" | head -20
    ;;
  *)
    echo "Skipped launchctl bootstrap. You can run it later after reviewing the plist."
    ;;
esac
