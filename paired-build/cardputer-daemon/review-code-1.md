---
schema_version: 1
review_for: code at commit 166660d1f1cbb44595333f344aac22035ac103f9
iteration: 1
reviewer: cc
timestamp: 2026-05-12T14:15:00Z
judgment_call: false
summary: >
  实施 5 切片 5 commit + 12/12 单元测试通过 + integration smoke 端到端通过。代码扎实，对齐 PLAN.md 所有关键决策（A-K + 切片 0-6）。无 blocker，3 个 nit 不阻塞。
---

issues:
  - type: nit
    id: CODE-hook-python-startup
    where: hook_to_daemon.sh
    issue: 每次 hook 触发跑 3 个独立 python3 子进程（解析+加type字段、提 hook_event_name、提 session_id、socket send），冷启动开销叠加。
    why: macOS Python 3.14 冷启动 50-100ms × 3 = 150-300ms 每 hook 触发；CC 一个 session 一天可能 30+ 次 hook，开销虽小但可合并。
    fix: 把整套逻辑合成单一 python 调用（解析输入 → 加 type=hook → 写 socket → 全在一个 python 进程内）。v0.1 接受当前实现（可读性高、故障隔离好），列为 follow-up。
  - type: nit
    id: CODE-ble-on-disconnect-redundant
    where: ble_client.py:113-114
    issue: run_forever 主循环 finally 块在 device is None 时仍调 on_disconnected(None)，状态先被设 backoff 再被设 disconnected，callback 触发两次。
    why: device 未找到时 state 已经 set 为 backoff（line 94），紧接着 continue 走 finally 又 set disconnected（callback 重发）。功能不影响（最终状态正确），但 callback 观察者会看到双重事件。
    fix: finally 中加 `if self.state not in ("backoff", "scanning"): await on_disconnected(...)`；或者把 on_disconnected 内的 _set_state 改成 idempotent guard。v0.1 接受。
  - type: nit
    id: CODE-socket-malformed-silent
    where: socket_server.py:71-72
    issue: malformed JSON / non-dict 消息静默 return，没记 WARN 日志。
    why: PLAN.md §5.1 明确"JSON 解析失败：daemon 丢弃，WARN 日志（不退出）"。当前实现丢弃但无 log。
    fix: 在 except json.JSONDecodeError / non-dict 分支加 `logging.warning("ignored malformed socket message: %r", raw[:80])`。v0.1 影响排查体验但不功能性。
