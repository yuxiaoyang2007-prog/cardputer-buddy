### Shell: `'date -u +%Y-%m-%dT%H:%M:%SZ'`
2026-05-12T13:34:32Z

---
schema_version: 1
review_for: PLAN.md
iteration: 3
reviewer: codex
timestamp: 2026-05-12T13:34:32Z
judgment_call: true
summary: >
  iteration-2 的 1 个 blocker 和 2 个 suggestion 已基本落地，当前没有新的 blocker。
  剩余问题是两个实现级歧义，建议在进入编码前收口。
---
issues:
  - type: suggestion
    id: PLAN-3.D-FALLBACK-PATH
    where: PLAN.md §3 决策 D
    issue: fallback log rotation 写了 5MB cap，但 mv 示例使用相对路径。
    why: stat 检查的是 ~/.cardputer-daemon/hook-fallback.log，随后 mv hook-fallback.log hook-fallback.log.1 依赖当前工作目录；hook 的 cwd 不保证是 ~/.cardputer-daemon，按字面实现会导致目标日志不被 rotate。
    fix: 统一定义 LOG="$HOME/.cardputer-daemon/hook-fallback.log"，mkdir -p "$(dirname "$LOG")"，超过 5MB 时 mv -f "$LOG" "$LOG.1"，再 append 到 "$LOG"。
  - type: suggestion
    id: PLAN-5.5-STATUS-PATH
    where: PLAN.md §4 / §5.3 / §6 切片 2
    issue: status 请求的处理路径前后不一致。
    why: §5.3 和切片 4 写 event_consumer 派发 status，切片 2 又写 socket_server 直接回 status_reply；如果目标是不让 session_store 的读写路径分叉，需要明确 status 也经 queue+future，或者明确 socket_server 只通过只读 callback 取快照。
    fix: 选定一种路径并统一全文；更贴合当前单 consumer 设计的是 socket_server 收到 status 后投递带 Future 的 status event，由 event_consumer 生成快照并 set_result。
