#!/bin/bash
# Claude Code statusline that captures rate_limits for the Cardputer daemon.
#
# Two modes:
#   1. Wrapper mode (default): captures rate_limits to ~/.cardputer-daemon/usage.json,
#      then forwards stdin to a downstream statusline command (e.g. claude-hud) and
#      relays its output. Set CARDPUTER_STATUSLINE_DOWNSTREAM to the downstream command.
#   2. Standalone mode: if no downstream command is set, prints a basic status line
#      (model + 5h%/7d%).
#
# Configure in ~/.claude/settings.json:
#   "statusLine": { "type": "command", "command": "bash '/path/to/cardputer/scripts/statusline.sh'" }

set -e

USAGE_FILE="$HOME/.cardputer-daemon/usage.json"
INPUT=$(cat)

mkdir -p "$(dirname "$USAGE_FILE")"
TMP="$USAGE_FILE.tmp.$$"
if command -v jq >/dev/null 2>&1; then
  echo "$INPUT" | jq -c '.rate_limits // {}' > "$TMP" 2>/dev/null || echo '{}' > "$TMP"
else
  echo '{}' > "$TMP"
fi
mv "$TMP" "$USAGE_FILE"

DOWNSTREAM="$HOME/.cardputer-daemon/downstream-statusline.sh"
if [ -x "$DOWNSTREAM" ]; then
  echo "$INPUT" | "$DOWNSTREAM"
elif command -v jq >/dev/null 2>&1; then
  MODEL=$(echo "$INPUT" | jq -r '.model.display_name // .model.id // "claude"' 2>/dev/null)
  FIVE=$(echo "$INPUT" | jq -r '.rate_limits.five_hour.used_percentage // empty' 2>/dev/null)
  WEEK=$(echo "$INPUT" | jq -r '.rate_limits.seven_day.used_percentage // empty' 2>/dev/null)
  OUT="$MODEL"
  [ -n "$FIVE" ] && OUT="$OUT  5h:$(printf '%.0f' "$FIVE")%"
  [ -n "$WEEK" ] && OUT="$OUT  7d:$(printf '%.0f' "$WEEK")%"
  echo "$OUT"
else
  echo "claude"
fi
