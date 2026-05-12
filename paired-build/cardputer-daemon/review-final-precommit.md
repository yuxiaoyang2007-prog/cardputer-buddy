### Shell: `'git status --short --branch'`
git: warning: confstr() failed with code 5: couldn't get path of DARWIN_USER_TEMP_DIR; using /tmp instead
git: error: couldn't create cache file '/tmp/xcrun_db-XI2aSzZV' (errno=Operation not permitted)
git: warning: confstr() failed with code 5: couldn't get path of DARWIN_USER_TEMP_DIR; using /tmp instead
git: error: couldn't create cache file '/tmp/xcrun_db-AwhIbBVs' (errno=Operation not permitted)
## main
?? paired-build/cardputer-daemon/codex-final-review-prompt.md
?? paired-build/cardputer-
### Shell: `"git ls-files 'paired-build/cardputer-daemon/codex-final-review-prompt.md' 'paired-build/cardputer-daemon/review-code-1.md' 'paired-build/cardputer-daemon/codex-impl-prompt-resume.md'"`
git: warning: confstr() failed with code 5: couldn't get path of DARWIN_USER_TEMP_DIR; using /tmp instead
git: error: couldn't create cache file '/tmp/xcrun_db-S4l37YEA' (errno=Operation not permitted)
git: warning: confstr() failed with code 5: couldn't get path of DARWIN_USER_TEMP_DIR; using /tmp instead
git: error: couldn't create cache file '/tmp/xcrun_db-uAuxb0ST' (errno=Operation not permitted)

### Shell: `"date -u '+%Y-%m-%dT%H:%M:%SZ'"`
2026-05-12T14:17:13Z

---
schema_version: 1
review_for: code at commit 166660d1f1cbb44595333f344aac22035ac103f9
iteration: 1
reviewer: codex
timestamp: 2026-05-12T14:17:13Z
judgment_call: false
summary: >
  Not ready for main as-is. Core daemon flow is coherent across decisions A/F/K: session state mutates through one consumer, status uses queue+Future, and stale socket cleanup is after flock+connect probe. One blocker remains in the documented Claude Code hook config: the repo path contains a space, but README shows it unquoted, so copied hooks will likely fail before hook_to_daemon.sh runs.

issues:
  - type: blocker
    id: FINAL-README-HOOK-COMMAND-SPACE
    where: README-daemon.md:63
    issue: >
      The settings.json example uses `/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh` as a bare hook command even though the path contains a space.
    why: >
      Claude Code hook `command` entries are shell commands. A bare path with `Claude Code` will be split by the shell, so the configured hooks can fail with `/Users/xiaoyangyu/Claude: not found`. That breaks the main daemon data path despite daemon/socket/BLE code being implemented.
    fix: >
      Change every example command to a shell-safe form such as `"/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"` inside the JSON string, or `bash "/Users/xiaoyangyu/Claude Code/cardputer/hook_to_daemon.sh"`.

  - type: suggestion
    id: FINAL-SMOKE-PRODUCTION-SOCKET
    where: scripts/integration_smoke.sh:5
    issue: >
      integration_smoke.sh uses the production socket path under `~/.cardputer-daemon/control.sock` and does not verify that its background daemon actually acquired the lock before sending smoke events.
    why: >
      If the LaunchAgent daemon is already running, the spawned daemon exits, but the script can still send smoke SessionStart/UserPromptSubmit/Stop events into the live daemon, polluting counters and device state.
    fix: >
      Before sending smoke events, assert the background PID is still alive and owns the expected socket, or make the daemon socket path env-configurable so smoke can run against an isolated temporary socket.

  - type: suggestion
    id: FINAL-INSTALL-PLIST-DIFF-FIRST
    where: scripts/install_daemon.sh:29
    issue: >
      install_daemon.sh writes `~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist` before showing a diff or asking for confirmation.
    why: >
      The project CLAUDE.md config safety rule requires read/diff/confirm before key config changes. The script asks before bootstrap, but the LaunchAgent plist has already been created or overwritten.
    fix: >
      Render to a temp file first, show a diff against the existing plist or note that it is new, then write `PLIST_PATH` only after user confirmation.

  - type: nit
    id: FINAL-SOCKET-DROP-WARN
    where: socket_server.py:71
    issue: >
      Malformed JSON, non-dict messages, unknown message types, and unknown hook names are silently dropped.
    why: >
      PLAN.md section 5.1 says these cases should be discarded with WARN logs. This mainly affects debugging, not the successful hook path.
    fix: >
      Add warning logs for JSON decode failure, non-dict input, unknown `type`, and invalid `hook_event_name`.

  - type: nit
    id: FINAL-BLE-DISCONNECT-CALLBACK-DUP
    where: ble_client.py:112
    issue: >
      run_forever calls on_disconnected in finally whenever not connected, including scan-miss/backoff paths and paths where the bleak disconnected callback already set disconnected.
    why: >
      State observers can see redundant backoff/disconnected or disconnected/disconnected transitions. Functionality remains intact.
    fix: >
      Guard the finally block so it only emits disconnected for a real connected-client teardown, or make `_set_state` idempotent.

  - type: nit
    id: FINAL-HOOK-PYTHON-OVERHEAD
    where: hook_to_daemon.sh:29
    issue: >
      The hook wrapper starts multiple Python processes per hook and passes JSON through environment variables.
    why: >
      This adds avoidable hook latency and can fail for unusually large UserPromptSubmit payloads due to exec environment size limits.
    fix: >
      Collapse parse, metadata extraction, socket send, and fallback logging into one Python invocation that reads the hook JSON from stdin.
