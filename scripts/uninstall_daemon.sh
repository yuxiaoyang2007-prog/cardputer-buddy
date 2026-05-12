#!/usr/bin/env bash
set -euo pipefail

PLIST_PATH="${HOME}/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist"

echo "This will unregister LaunchAgent if loaded and remove:"
echo "$PLIST_PATH"
echo "It will keep ${HOME}/.cardputer-daemon/ for logs, socket, and venv."
read -r -p "Continue uninstall? [y/N] " answer
case "$answer" in
  y|Y|yes|YES)
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "Uninstalled cn.joulian.cardputer-daemon"
    ;;
  *)
    echo "Uninstall skipped."
    ;;
esac
