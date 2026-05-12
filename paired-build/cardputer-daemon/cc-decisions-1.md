---
schema_version: 1
for_review: review-plan-1.md
iteration: 1
timestamp: 2026-05-12T13:30:00Z
---

decisions:
  - id: META-RUNNER-PREFIX
    type: meta
    decision: deferred
    action: review-plan-1.md 顶部含 6 行 ask_codex.sh runner 的工作日志（Shell 命令记录 + 思考过程），不是 reviewer 主动违反 schema 而是 runner 设计选择（ask_codex.sh:311-329 把 command_execution / agent_message 都写进 -o 文件）。CC 接受第一个 `---` 之前的 runner 元数据，从 `---` 开始按 schema 解析。
    rationale: 重跑 codex 仍会带 shell log（runner 行为）→ 陷入卡死信号。这是 cc-codex skill 与 ask_codex.sh runner 接口的已知 gap，应在 cc-codex skill 升级时由 runner 侧修。本任务记录为已知偏离，不阻塞流程。
  - id: META-YAML-QUOTE
    type: meta
    decision: deferred
    action: review-plan-1.md 中 3 个 issue id 字段（PLAN-5.1-SOCKET / PLAN-6.5 / PLAN-3.D-JSON）末尾有未匹配双引号，是 codex 输出的 yaml 语法噪音。CC 容忍并按字面 id 比对（去尾引号）。
    rationale: 11/13 issue 内容扎实可解析；为单纯 yaml 引号噪音重跑成本高。下轮 prompt 加严提示要求 id 字段不带任何引号。
  - id: PLAN-SEC.1
    type: blocker
    decision: rejected
    action: 不改 PLAN。review prompt 模板把"指令性语句"宽泛理解，把项目 spec 里的"必须/不许"也当注入识别。这是 cc-codex review prompt 模板的过度敏感问题，不是 PLAN 内容错误。
    rationale: UNTRUSTED_DATA 块里的内容是项目 CLAUDE.md 节选（描述性规则），不含"忽略以上"、"现在你应该"等真正的注入语义。下轮 prompt 缩窄"指令性语句"定义，只对真正的角色切换 / 新任务覆盖触发。
  - id: PLAN-3.B
    type: blocker
    decision: fixed
    action: 改 PLAN §3 决策 B + §5.3 + §6 切片 4：(a) 实施前先在用户机器上验证 SessionEnd 是否真触发；(b) 不论结果，session_store 加 inactivity TTL（30 分钟无事件 → 视为已结束，自动从 sessions 字典移除）；(c) daemon 重启后未知 session_id 来的 Stop / UserPromptSubmit 走 upsert 路径（决策 C 已覆盖）。
  - id: PLAN-3.C
    type: blocker
    decision: fixed
    action: 改 PLAN §3 决策 C + §5.3：apply_event 改成幂等 upsert——任何带 session_id 的事件都可创建或修正 session；记录 last_seen timestamp；未知 session_id 的 Stop / UserPromptSubmit 自动新建 session 并更新状态。新增单元测试覆盖乱序到达、daemon 重启后接 Stop / 接 UserPromptSubmit 两种 unknown-session 场景。
  - id: PLAN-3.D
    type: blocker
    decision: fixed
    action: 改 PLAN §3 决策 D + §5.1：(a) hook wrapper 用 nc -U 或 python one-liner 写 socket，加 200ms connect/write timeout，失败时本地 stderr append 到 $HOME/.cardputer-daemon/hook-fallback.log，不阻塞 CC；(b) daemon 端 socket_server 用 asyncio drain，写满时 backpressure 通过 OS socket buffer 自然形成；(c) session_store 加 30 分钟 inactivity TTL 自动清理孤儿 session（即使 hook 丢事件状态也最终一致）。
  - id: PLAN-5.1
    type: blocker
    decision: fixed
    action: 改 PLAN §5.1 + §4 模块边界：socket_server 只负责解析 JSON 后投递到 asyncio.Queue；daemon 启动单一 consumer task 顺序处理 apply_event + compute_heartbeat + BLE send_line。删除"unix socket 自然串行 → 不需要 daemon 端额外锁"的错误结论。
  - id: PLAN-3.A
    type: blocker
    decision: fixed
    action: 改 PLAN §3 决策 A + §6 切片 3：ble_client 维护 last_heartbeat + dirty flag；send 失败只标记 dirty 不丢状态；reconnect callback 触发后立即重发 last_heartbeat。新增单元测试覆盖"disconnected 期间收 3 个 hook 事件 → reconnect 后只发最新聚合帧"。
  - id: PLAN-7.1
    type: blocker
    decision: fixed
    action: 改 PLAN §7：删除 pkill -9 / kill 字样。重启测试改用 `launchctl kickstart -k gui/$(id -u)/cn.joulian.cardputer-daemon`（kickstart -k 直接 restart）；如必须按 PID 操作，先 `launchctl print gui/$(id -u)/cn.joulian.cardputer-daemon | grep pid`，把 PID 列给用户确认再操作。
  - id: PLAN-3.E
    type: suggestion
    decision: fixed
    action: 改 PLAN §3 决策 E + §8 + §6 切片 5：install_daemon.sh 创建 ~/.cardputer-daemon/venv（python -m venv），pip install bleak 进 venv；plist ProgramArguments 指向 venv 的 python3；脚本最后跑 `venv/bin/python -c "import bleak; print(bleak.__version__)"` 验证后再 launchctl bootstrap。
  - id: PLAN-3.J
    type: suggestion
    decision: fixed
    action: 改 PLAN §3 决策 J：保留 notify_stop.sh 不动；新增 hook_to_daemon.sh 作为 daemon 路径的 hook wrapper；用户在 settings.json hooks 配置里把命令从 notify_stop.sh 改为 hook_to_daemon.sh（手工 diff 后），不自动覆盖。
  - id: PLAN-5.1-SOCKET
    type: suggestion
    decision: fixed
    action: 改 PLAN §5.1 + §6 切片 4：daemon 启动严格按 5 步走——(1) mkdir -p ~/.cardputer-daemon/ 0700；(2) open daemon.lock + fcntl.flock LOCK_EX|LOCK_NB；(3) 探测 control.sock 是否可连（connect timeout 100ms）；(4) 仅当不可连接才 unlink；(5) bind + chmod 0600 + listen。
  - id: PLAN-3.K
    type: suggestion
    decision: fixed
    action: 改 PLAN §3 决策 K + §6 切片 4：daemon socket 协议加 `{"type": "status"}` 请求，daemon 返回一行 JSON 含 BLE 连接状态 / sessions 字典 dump / last_heartbeat / last_send_error / 启动时间。新增 `scripts/cardputer-daemon-status.sh`：cat socket + jq 美化输出，README 列为故障排查入口。
  - id: PLAN-6.5
    type: nit
    decision: fixed
    action: 改 PLAN §6 切片 5：明确使用 `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`，不是 bootterap（原文档拼写错）。
  - id: PLAN-3.D-JSON
    type: nit
    decision: fixed
    action: 改 PLAN §3 决策 D：把 JSON 示例改成两份——(a) 文档用伪代码 / TypeScript 接口签名描述字段；(b) 给一份无注释、无 union 表达式的真实 JSON 示例可 jq . 验证。
