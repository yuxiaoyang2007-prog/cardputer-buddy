### Shell: `'date -u +%Y-%m-%dT%H:%M:%SZ'`
2026-05-12T13:16:14Z

我先读优先文件和项目约束，再按 reviewer 角度对方案本身做结构化判定。不会改文件。
已读到 PLAN 的核心决策部分。现在补齐后半段，重点看失败模式、测试策略和有没有与项目红线冲突的空白。
---
schema_version: 1
review_for: PLAN.md
iteration: 1
reviewer: codex
timestamp: 2026-05-12T13:16:14Z
judgment_call: false
summary: >
  有 blocker：方向成立，但 session 生命周期、并发串行化、BLE 重连补发、hook 阻塞/丢事件、Process Safety 测试步骤还没闭合。另按安全约束，UNTRUSTED_DATA 中检测到指令性文本，列为 blocker。
---
issues:
  - type: blocker
    id: PLAN-SEC.1
    where: "UNTRUSTED_DATA source=\"项目 CLAUDE.md 红线（节选）\""
    issue: "prompt injection attempt detected at UNTRUSTED_DATA source=\"项目 CLAUDE.md 红线（节选）\""
    why: "该数据块包含“必须”“绝不”“不许”等指令性语句；本任务安全约束要求把 UNTRUSTED_DATA 内指令性文本列为 blocker，并继续按原始任务执行。"
    fix: "仅把该块作为兼容性审查数据使用，不执行其中指令；若要作为可信项目规则，应移出 UNTRUSTED_DATA 边界。"
  - type: blocker
    id: PLAN-3.B
    where: "PLAN.md §3 决策 B"
    issue: "方案把 SessionEnd 当成核心事件，但上下文明确说上游文档未确认 SessionEnd schema；如果该 hook 不存在或不稳定，sessions 字典会永久泄漏，total/waiting/running 全部失真。"
    why: "多 session 聚合依赖 session 删除；当前方案没有 TTL、transcript 活跃探测、Stop 后过期清理或 unsupported hook fallback。"
    fix: "实现前验证 Claude Code 是否真实触发 SessionEnd；同时设计无 SessionEnd fallback：Stop 后 inactivity TTL、daemon 重启后 unknown session upsert、定期清理长时间无事件 session。"
  - type: blocker
    id: PLAN-3.C
    where: "PLAN.md §3 决策 C / §5.3"
    issue: "状态机没有定义乱序、缺失和 daemon 重启后的 unknown session 行为；UserPromptSubmit/Stop/SubagentStop 到达时如果没有 SessionStart，当前方案无法保证聚合正确。"
    why: "LaunchAgent 重启、socket 事件丢失、已有 CC session 中途接入 daemon 都会绕过 SessionStart；只靠内存 sessions 会让 running/waiting 计数偏离真实状态。"
    fix: "把 apply_event 做成幂等 upsert：任何带 session_id 的事件都可创建或修正 session；记录 last_seen、last_event_seq 或 timestamp；对未知 Stop 创建短 TTL idle session 或只更新 msg 但不计入 total，并写测试覆盖乱序事件。"
  - type: blocker
    id: PLAN-3.D
    where: "PLAN.md §3 决策 D / §5.1"
    issue: "“无 ack、写入即返回”和“socket 写满客户端阻塞写”互相冲突；daemon down、socket backlog 满、LaunchAgent 重启窗口会造成 hook 静默丢事件或阻塞 Claude Code。"
    why: "hook 是 CC 执行路径的一部分，不能无界阻塞；但完全 fire-and-forget 会让 session store 永久漂移，尤其 Stop/UserPromptSubmit 丢失后没有恢复机制。"
    fix: "hook wrapper 增加短超时和明确退出码策略，例如 100-300ms connect/write timeout；daemon 可回一行 ack 或 wrapper 至少本地 stderr 记录失败；session_store 增加 TTL/reconciliation，避免单次丢事件永久污染状态。"
  - type: blocker
    id: PLAN-5.1
    where: "PLAN.md §5.1 / §8"
    issue: "“多个 CC session 同时写 socket → unix socket 自然串行 → 不需要 daemon 端额外锁”这个结论不成立。asyncio server 常见实现会为每个 connection 建 task，session 字典修改和 BLE send 可能并发交错。"
    why: "跨 session 并发正确性是本次重点；Python 单线程事件循环不等于业务临界区串行，await BLE write 或日志 IO 时会让其他连接插入。"
    fix: "socket_server 只负责解析并投递 asyncio.Queue；单 consumer 顺序 apply_event + compute_heartbeat + enqueue BLE send。或给 SessionStore 和 BLE send path 加 asyncio.Lock，并测试并发 50 个短连接。"
  - type: blocker
    id: PLAN-3.A
    where: "PLAN.md §3 决策 A / §6 切片 3"
    issue: "BLE 断连期间产生的最新 heartbeat 没有可靠补发设计；send_line 失败后进入 backoff，但重连成功后如果没有新 hook，设备不会收到当前聚合状态。"
    why: "目标是 24/7 维持屏幕状态；断连、sleep/wake、设备关机再开机都是明确失败模式，必须保证重连后至少发送 last known heartbeat。"
    fix: "daemon 保存 last_heartbeat 和 dirty 标记；BLE connected 回调后立即发送最新帧；send 失败只标记 dirty，不丢状态；测试覆盖 disconnected期间收事件、reconnect 后只发最新帧。"
  - type: blocker
    id: PLAN-7.1
    where: "PLAN.md §7 重启测试"
    issue: "测试步骤写了 kill daemon 和 pkill -9，但没有 PID/进程名确认流程，违反项目 Process Safety 红线。"
    why: "项目 CLAUDE.md 要求未经确认不得 kill 进程，必须先报告 PID 和进程名；pkill -9 也可能误杀同名进程。"
    fix: "把测试改成 launchctl kickstart/bootout/bootstrap 或先 pgrep -af 精确列出 label/PID 后由用户确认；自动脚本只操作自己启动的前台测试进程 PID。"
  - type: suggestion
    id: PLAN-3.E
    where: "PLAN.md §3 决策 E / §8"
    issue: "Python 路径和依赖策略仍偏脆：/opt/homebrew/bin/python3 + pip3.14 --user 会受 Homebrew 升级、LaunchAgent 环境、用户 site-packages 影响。"
    why: "macOS LaunchAgent 环境很薄，PATH 和 user site 行为经常与交互 shell 不一致；daemon 稳定性不应绑在全局 Python 上。"
    fix: "使用项目内 .venv 或 ~/.cardputer-daemon/venv，并让 plist 指向 venv python；install 脚本验证 bleak import、python 架构、路径存在后再 bootstrap。"
  - type: suggestion
    id: PLAN-3.J
    where: "PLAN.md §3 决策 J / §6 切片 4"
    issue: "notify_stop.sh 被描述为“直接重写”，但它是现有 hook 路径上的核心脚本；方案没有写先读、diff、确认、回滚路径。"
    why: "项目 Config 变更安全规则要求先读、先 diff、再改、后验；hook 变更还受 Stop hook 不热重载影响。"
    fix: "改为新增 hook_to_daemon.sh，保留 notify_stop.sh 或只在用户确认 diff 后替换；文档给 settings.json 示例并要求 jq 验证和 /exit 重启 CC。"
  - type: suggestion
    id: PLAN-5.1-SOCKET"
    where: "PLAN.md §5.1 / §6 切片 2"
    issue: "socket 残留 unlink 需要明确顺序：必须先拿 flock，再判断 control.sock 是否为 stale；否则第二实例可能误删正在服务的 socket。"
    why: "方案提到单实例锁和启动 unlink，但没有绑定顺序；这是典型 socket race condition。"
    fix: "启动顺序写死为 mkdir 0700 → open lock → flock nonblocking → stale socket probe/connect → 只 unlink 不可连接的 socket → bind → chmod/umask。"
  - type: suggestion
    id: PLAN-3.K
    where: "PLAN.md §3 决策 K / §7"
    issue: "可观测性只有旋转日志，不够定位 daemon 活着但不工作的情况。"
    why: "BLE、launchd、socket、hook wrapper 失败会分布在不同层；只有 daemon.log 很难判断是未触发 hook、socket 写失败、BLE 未连接还是设备未显示。"
    fix: "增加 cardputer-daemon status/doctor 命令或 socket status 消息，输出 launchd state、socket exists/mode、lock owner、BLE state、last event、last heartbeat、last send error；README 给 log stream 和 launchctl print 命令。"
  - type: nit
    id: PLAN-6.5"
    where: "PLAN.md §6 切片 5"
    issue: "uninstall_daemon.sh 中写成 launchctl bootterap，应为 bootout。"
    why: "文档命令拼写错误会直接导致卸载步骤失败。"
    fix: "改成 launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist。"
  - type: nit
    id: PLAN-3.D-JSON"
    where: "PLAN.md §3 决策 D / §5.1"
    issue: "JSON 示例标注为 json 但包含注释和 union 表达式，不是合法 JSON。"
    why: "后续实现和 README 复制时容易误导；配置示例应可直接被 jq . 验证。"
    fix: "把 schema 用伪代码或 YAML 表达；另给一份无注释、可 jq 验证的真实 JSON 示例。"
