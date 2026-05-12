---
schema_version: 1
for_review: review-plan-3.md
iteration: 3
timestamp: 2026-05-12T13:40:00Z
---

decisions:
  - id: META-RUNNER-PREFIX
    type: meta
    decision: deferred
    action: review-plan-3.md 顶部仍有 2 行 ask_codex.sh runner shell log（`### Shell: 'date...'`、ISO 时间戳）。frontmatter 干净（从第一个 `---` 开始即 schema 内容）。继承 iteration-1 决定：runner-prefix 不计入 reviewer schema 违规。
    rationale: 此噪音是 runner 设计，根除需改 cc-codex skill 或 ask_codex.sh runner 行为，超出本任务范围。
  - id: PLAN-3.D-FALLBACK-PATH
    type: suggestion
    decision: fixed
    action: 改 PLAN §3 决策 D：hook_to_daemon.sh 顶部定义 `LOG="$HOME/.cardputer-daemon/hook-fallback.log"`，`mkdir -p "$(dirname "$LOG")"`，size 检查用 `[ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ] && mv -f "$LOG" "$LOG.1"`，再 append 到 "$LOG"。所有路径绝对化，不依赖 cwd。
    rationale: codex 指出的是真实 bug——hook 触发时 cwd 是 CC 启动的目录（不可控）。绝对路径修复成本极低，正确性收益大。
  - id: PLAN-5.5-STATUS-PATH
    type: suggestion
    decision: fixed
    action: 改 PLAN §4 + §5.5 + §6 切片 2 + 切片 4：status 请求**统一走 event_queue + Future**。socket_server 收到 status → 构造 `{"type":"status", "future": <asyncio.Future>}` 投递到 queue → event_consumer 处理时生成快照 + future.set_result(snapshot) → socket_server 把 future 结果写回 socket。所有 session_store / last_heartbeat 读访问都在 event_consumer 单一 task 内。
    rationale: 统一架构 > "看起来不需要锁"的特例化。codex 给的两个选项里，"socket_server 直接通过只读 callback 取快照"也成立（asyncio 单线程下读不可能撕裂），但分叉路径会让"单 consumer 解决并发"这个不变式不再可证。统一走 queue 让单元测试更简单（同一种事件机制），代价是多一次上下文切换（微秒级，可忽略）。
