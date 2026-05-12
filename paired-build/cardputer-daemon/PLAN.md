# Cardputer Daemon 设计方案

## 1. 目标

为 M5 Cardputer Adv 写一个常驻 macOS 后台进程（LaunchAgent 自启），24/7 维持到 Cardputer 的 BLE 连接，把多个并发 Claude Code session 的活动状态聚合后实时推到设备屏幕。解决当前 Stop hook 直连 BLE 写一帧就断（"通知一闪就没"、并发 session 抢 BLE）的问题。

## 2. 非目标

- **不改设备端固件**。`buddy/device/buddy_protocol.py` 心跳格式、`buddy_ui_cp.py` 屏幕渲染保持不动（B 阶段刚刚 push 完，避免重 push）。
- **不动 Claude Desktop**。设备 + 这个 daemon 形成独立闭环，不依赖 Claude Desktop 的 Hardware Buddy。
- **不接 outbound（设备 → host）控制语义**（permission once/deny、unpair 等）。daemon 是单向 host→device 心跳通道；设备端 outbound 协议保留但当前 daemon 不解释。
- **不做 ESP32-C6 / 其他硬件适配**。只针对 BLE 名 `Claude_984552`、NUS service 6e400001-…、RX UUID 6e400002-…。
- **不做跨机器**。daemon 跑在 Mac mini，Stop hook 触发也在 Mac mini，不考虑 Tailscale 远端 CC session。
- **不实现真实 token 计数**。`tokens_today` / `entries` 字段保留可填，但 v0.1 计算口径是"daemon 收到的 hook 事件累计计数 / 当日累计"——不解析 transcript_path 反推真实 token。
- **不做 GUI / menu bar**。clawd-tank 那个是 nice-to-have，v0.1 没有。

## 3. 关键决策

### 决策 A：BLE 连接策略 = 持续连接 + 指数 backoff + reconnect 补发

**选**：daemon 启动后立刻扫描连接，连接断开/失败后按 2s → 4s → 8s → … → 60s（上限）backoff 重试，重试 cap 后稳定在 60s。设备没开机时也按这个节奏轻量轮询。

**断连期间状态保留 + reconnect 补发**：
- `ble_client` 持有 `last_heartbeat: dict | None` 和 `dirty: bool`。
- send_line 失败 → 只标记 `dirty = True`，**不丢 last_heartbeat**。
- 断连期间 daemon 主循环正常 apply_event + compute_heartbeat → 写入 last_heartbeat（dirty = True）。
- BLE reconnect 回调触发后，若 `dirty`：立即 write_gatt_char(last_heartbeat) + `dirty = False`。

**替代方案 + 拒绝原因**：
- *按需连接*（收到 hook 消息才连）：解决不了"一闪就没"——这就是当前 bridge.py 的行为。拒绝。
- *心跳间空闲断开*（连接 30s 内有消息保持，无消息断开）：复杂度高、状态机难写、收益小（BLE 静态连接功耗几乎可忽略）。拒绝。
- *按需+保持* hybrid：增加状态机分支，不如 24/7。拒绝。

### 决策 B：接 5 个 CC hook 事件 + 30 分钟 inactivity TTL 兜底

**选**：SessionStart / SessionEnd / UserPromptSubmit / Stop / SubagentStop。

| 事件 | daemon 怎么用 |
|------|---------------|
| SessionStart | upsert session_id 到 `sessions` 字典，状态 `idle`，记 cwd / started_at / last_seen |
| UserPromptSubmit | upsert + 切到 `running`，msg = "🤖 working in <cwd basename>" |
| Stop | upsert + 切到 `idle`，msg = "✦ done in <cwd basename>" |
| SubagentStop | upsert + 不改 state，刷新 msg = "🪶 subagent done"，更新 last_seen |
| SessionEnd | 从 `sessions` 移除 session_id（如果触发） |

**SessionEnd 不触发场景的兜底**：上游官方文档未明确 SessionEnd 的 input schema 是否触发；为防永久 session 泄漏，**daemon 后台 cron 每分钟扫描 sessions 字典，把 `now - last_seen > 30 min` 的 session 自动移除**。这条 TTL 让"上游不触发 SessionEnd"和"hook 丢事件"两种场景下系统最终一致。

**实施前验证**：切片 1 开工前在用户 Mac mini 跑一次实测——配置一个临时 SessionEnd hook 写文件，开关一个 CC session 看是否触发。结果记入 PLAN.md 附录或 SUMMARY.md。

**替代方案 + 拒绝原因**：
- *只接 Stop*（B-mini）：聚合数会不准——SessionStart 不接就不知道总 session 数，UserPromptSubmit 不接就不知道 running 数。"聚合+最新"必须接齐至少这 4-5 个。
- *再加 PreToolUse / PostToolUse*：每个工具调用都触发太吵，对屏幕没用（屏幕一秒刷几十次也看不清），还增加 hook 开销。拒绝。
- *接 StopFailure*：上游文档没确认 schema，作为 follow-up。v0.1 不接。

### 决策 C：聚合算法 + apply_event 幂等 upsert + 当日重置

**所有事件走幂等 upsert**：任何带 session_id 的事件都可创建或修正 session 记录。未知 session_id 来的 Stop / UserPromptSubmit / SubagentStop 不丢弃，而是自动创建 session（state 按事件语义设：UserPromptSubmit → running，Stop → idle，SubagentStop → idle）。这覆盖三种场景：
1. daemon 重启后已有 CC session 中途接入
2. SessionStart hook 丢事件
3. socket 写入失败后续 hook 恢复

每次事件后 daemon 重新计算并下发一帧心跳：

```python
def compute_heartbeat() -> dict:
    return {
        "msg": latest_event_msg,
        "total": len(sessions),
        "running": sum(1 for s in sessions.values() if s.state == "running"),
        "waiting": sum(1 for s in sessions.values() if s.state == "idle"),
        "tokens": tokens_today,
        "tokens_today": tokens_today,
        "entries": entries_today,
    }
```

**`tokens_today` 当前语义**：当日累计 hook 事件数。理由：设备屏幕字段是给视觉反馈用的，"活动量"比"真实 token"对玩具用途更有意义。

**`entries_today` 语义**：当日 UserPromptSubmit 累计数 = 用户当天发的 prompt 次数。

**当日重置策略**：daemon 内存里记 `today_date`（YYYY-MM-DD，本地时区），每次 apply_event 前对比，跨日则 `tokens_today = entries_today = 0`，并更新 today_date。

### 决策 D：IPC = Unix domain socket，JSON line protocol（含 hook 端 timeout + 本地降级）

**选**：`~/.cardputer-daemon/control.sock`（SOCK_STREAM，权限 0600，owner = user），daemon 监听，hook wrapper 短连接写一行 JSON 即关闭。

**hook → daemon 消息字段（伪代码）**：

```
HookMessage {
  type: "hook"                         // 必填，目前唯一值
  hook_event_name: "SessionStart" | "SessionEnd" | "UserPromptSubmit"
                 | "Stop" | "SubagentStop"   // 必填
  session_id: string                   // 必填，CC 提供
  cwd: string                          // 必填，CC 提供
  transcript_path: string              // 必填，CC 提供
  prompt?: string                      // 仅 UserPromptSubmit
  stop_hook_active?: bool              // 仅 Stop
  source?: "startup" | "resume" | "clear"  // 仅 SessionStart
}
```

**干净的 JSON 示例（可 jq . 验证）**：

```json
{"type":"hook","hook_event_name":"Stop","session_id":"abc123def456","cwd":"/Users/xiaoyangyu/projects/foo","transcript_path":"/Users/xiaoyangyu/.claude/projects/-Users-xiaoyangyu-projects-foo/abc.jsonl","stop_hook_active":false}
```

**hook wrapper 端的可靠性**：
- 写 socket 用 `nc -U` 或 Python one-liner，加 **200ms connect + 200ms write timeout**。
- 失败 → append 一行 `[YYYY-MM-DD HH:MM:SS] <event> <session_id> daemon-unreachable` 到 `$HOME/.cardputer-daemon/hook-fallback.log`，不阻塞 CC turn。
- **fallback log size cap（路径绝对化，不依赖 cwd）**：
  ```bash
  LOG="$HOME/.cardputer-daemon/hook-fallback.log"
  mkdir -p "$(dirname "$LOG")"
  if [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv -f "$LOG" "$LOG.1"
  fi
  printf '...\n' >> "$LOG"
  ```
  5MB 阈值，单份历史（.log.1），无外部 logrotate 依赖。
- daemon 不回 ack（hook 不等响应）。

**daemon 端的可靠性**：
- socket_server 用 asyncio drain，写满时由 OS socket buffer 自然 backpressure。
- session_store 的 30 分钟 inactivity TTL 保证即使 hook 丢事件，状态最终一致（决策 B / C）。

**替代方案 + 拒绝原因**：
- *写文件 + inotify*：文件 IPC 慢、要处理 race、清理麻烦。拒绝。
- *TCP localhost*：socket 文件天然能加 owner permission，TCP 没法。拒绝。
- *D-Bus / launchd port*：macOS 上 d-bus 不原生，launchd Mach port 复杂。拒绝。

### 决策 E：Python venv + LaunchAgent

- **venv**：`~/.cardputer-daemon/venv/`，由 `scripts/install_daemon.sh` 用 `/opt/homebrew/bin/python3 -m venv` 创建，pip install bleak（pin 版本）。
- **plist ProgramArguments**：`[<HOME>/.cardputer-daemon/venv/bin/python3, <HOME>/Claude Code/cardputer/daemon.py]`（实际路径替换占位符）。
- **label**：`cn.joulian.cardputer-daemon`
- **plist 路径**：`~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`
- **关键 plist 字段**：
  - `RunAtLoad: true` + `KeepAlive: true`（崩了自动拉起）
  - `StandardOutPath` / `StandardErrorPath` = `~/.cardputer-daemon/daemon.log`
  - `ThrottleInterval: 30`（崩了 30s 内不无限拉起）
- **安装方式**：`scripts/install_daemon.sh` 跑：
  1. 创建 ~/.cardputer-daemon/（0700）
  2. python -m venv venv + pip install bleak==<pinned>
  3. **验证 venv 可用**：`venv/bin/python -c "import bleak; print(bleak.__version__)"` 不报错
  4. 渲染 plist 模板（替换 HOME / 用户名占位符）→ ~/Library/LaunchAgents/
  5. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`
  6. `launchctl print gui/$(id -u)/cn.joulian.cardputer-daemon | head -20` 列状态供用户检查
- **CC 不自动 install**（涉及不可逆 LaunchAgent 写盘），由用户跑脚本。

### 决策 F：单实例锁 + socket 启动顺序

daemon 启动严格按下面 5 步走（顺序硬绑定，防 race）：

1. `mkdir -p ~/.cardputer-daemon/` (mode 0700)
2. open `daemon.lock` + `fcntl.flock(LOCK_EX | LOCK_NB)`；锁失败立即退出并日志说明
3. 探测 `control.sock` 是否可 connect（200ms timeout）
4. **仅当不可连接** 时 unlink；可连接说明已有 daemon 在跑（步骤 2 应该已经拦住但双保险）
5. bind + chmod 0600 + listen

### 决策 G：BLE 单实例独占（设备侧）

BLE 物理上一次只允许一个 host 连。daemon 占着 → bridge.py 手动跑会失败。这是预期行为，不是 bug。**bridge.py 保留作 CLI 工具，但文档说明 daemon 跑着时不要用它**。

### 决策 H：daemon 内态持久化 = 不做（重启就清零）

- `sessions` 字典：内存。daemon 重启时清空，靠 apply_event 幂等 upsert（决策 C）和 TTL（决策 B）让状态最终一致。
- `tokens_today` / `entries_today`：内存。daemon 重启时清零。
- 设备屏幕的"今日累计"会随 daemon 重启归零。**用户可接受**（v0.1 是玩具，不是审计）。

**替代方案**：写 `~/.cardputer-daemon/state.json`，daemon 启动恢复。**拒绝**：复杂度增加、写盘频率难拿捏、收益小。**列为 follow-up**。

### 决策 I：静音逻辑放 daemon 端

`~/.cardputer-mute` 文件存在 → daemon 收到 hook 事件后不下发心跳，但仍维护内部 `sessions` 状态。理由：hook wrapper 不需要文件检查就能跑得更快；逻辑集中在 daemon 便于将来扩展。

### 决策 J：旧 bridge.py / notify_stop.sh 处理（保留旧文件 + 新增 wrapper）

- **bridge.py**：保留作 CLI 调试工具，README 里加一段"daemon 跑着时不要用"。代码不动。
- **notify_stop.sh**：**保留不动**。新增 `hook_to_daemon.sh` 作为 daemon 路径的 hook wrapper（独立文件）。用户在 settings.json hooks 配置里手工把命令路径从 `notify_stop.sh` 改为 `hook_to_daemon.sh`，**改前用 diff 看清楚**（遵循项目 Config 变更安全规则）。
- **回滚路径**：把 settings.json hooks 命令改回 notify_stop.sh + /exit 重启 CC 即可。

### 决策 K：日志 + status 命令（可观测性）

- **位置**：`~/.cardputer-daemon/daemon.log`
- **rotation**：Python `logging.handlers.RotatingFileHandler`，5MB × 3 份。
- **级别**：INFO 常规、DEBUG 看 env `CARDPUTER_DAEMON_DEBUG=1`。
- **status 命令**：socket 协议加 `{"type": "status"}` 请求，daemon 回一行 JSON：
  ```
  {"type":"status_reply","ble_state":"connected","ble_last_send_error":null,
   "sessions":{"abc":{"state":"running","cwd":"/x","last_seen":...}},
   "tokens_today":17,"entries_today":3,"last_heartbeat":{...},
   "uptime_s":3600,"version":"v0.1"}
  ```
- **`scripts/cardputer-daemon-status.sh`**：cat 一行 status 请求到 socket + jq 美化输出。README 把它列为首要故障排查工具。

## 4. 数据流 / 模块边界

```
┌─ Claude Code session 1 ─┐
│  Stop hook              │─┐
└─────────────────────────┘ │
┌─ Claude Code session 2 ─┐ │
│  UserPromptSubmit hook  │─┼──→  hook_to_daemon.sh (200ms timeout)
└─────────────────────────┘ │       │ stdin: hook JSON
┌─ Claude Code session N ─┐ │       │ action: 加 type=hook → 写 socket → exit
│  SessionStart hook      │─┘       │ 失败 → ~/.cardputer-daemon/hook-fallback.log
└─────────────────────────┘         ↓
                              ~/.cardputer-daemon/control.sock
                                    │
                                    ↓
                       ┌──────────────────────────────────┐
                       │  cardputer_daemon.py             │
                       │                                  │
                       │  ┌─ asyncio event loop ─────────┐│
                       │  │                              ││
                       │  │ socket_server                ││
                       │  │ - accept → 解析 JSON         ││
                       │  │ - 投递到 event_queue         ││
                       │  │ - 处理 {"type":"status"}      ││
                       │  │                              ││
                       │  │ event_consumer (单一 task)   ││
                       │  │ - while: event = await queue ││
                       │  │ - 派 hook / prune_tick       ││
                       │  │ - session_store.apply_event  ││
                       │  │ - 算 heartbeat               ││
                       │  │ - ble_client.send_or_buffer  ││
                       │  │                              ││
                       │  │ ttl_ticker (独立 task,每分钟) ││
                       │  │ - 仅投递 {type:prune_tick}    ││
                       │  │   到 event_queue              ││
                       │  │ - 不直接改 sessions          ││
                       │  │ ble_client                   ││
                       │  │ - 持续连接 + backoff         ││
                       │  │ - last_heartbeat / dirty     ││
                       │  │ - reconnect 立即重发         ││
                       │  └──────────────────────────────┘│
                       └────────────┬─────────────────────┘
                                    │ BLE NUS RX write
                                    ↓
                       ┌──────────────────────────────┐
                       │  Cardputer (Claude_984552)   │
                       │  buddy_protocol on_line()    │
                       │  → buddy_ui_cp.update_heartbeat │
                       └──────────────────────────────┘
```

**并发模型要点**：socket_server 接受多个并发连接（每个 connection 一个 asyncio task），但所有解析后的 event（hook 事件）都投递到**唯一** `asyncio.Queue`；event_consumer 是**单一** task 串行处理。**TTL pruner 也走 event_queue**：独立 ttl_ticker task 每分钟只投递一个 `{"type":"prune_tick"}` 到 queue，由 event_consumer 同一个 task 处理 prune。session_store 任何修改 / heartbeat 计算 / BLE send 都在 event_consumer 单一 task 内串行，零并发交错。

模块清单：

| 模块 | 文件 | 职责 |
|------|------|------|
| daemon entry | `daemon.py` | asyncio 主循环、子模块装配、信号处理、单实例 flock、TTL 定时任务 |
| session store | `session_store.py` | sessions 字典 + apply_event（幂等 upsert）+ compute_heartbeat + TTL prune + 当日重置 |
| socket server | `socket_server.py` | listen + accept + 解析 JSON line + 推 event 到 asyncio.Queue + status 请求处理 |
| BLE client | `ble_client.py` | bleak 持续连接 + backoff + send_line（last_heartbeat + dirty）+ 状态回调 |
| 配置常量 | `daemon.py` 顶部 | name_prefix、UUID、路径、backoff 表、TTL 30 min |
| hook wrapper | `hook_to_daemon.sh` | stdin JSON → 加 hook_event_name field → 200ms timeout 写 socket → 失败 append fallback log → exit 0 |
| LaunchAgent | `cn.joulian.cardputer-daemon.plist.template` | 自启 |
| 安装脚本 | `scripts/install_daemon.sh` | mkdir + venv + pip + 验证 import + 渲染 plist + launchctl bootstrap + print state |
| 卸载脚本 | `scripts/uninstall_daemon.sh` | launchctl bootout + 删 plist + （可选）删 ~/.cardputer-daemon/ |
| 状态查询 | `scripts/cardputer-daemon-status.sh` | 写 status 请求到 socket + jq 美化 |
| settings.json patch 文档 | README-daemon.md 节 | 5 个 hook 事件 → hook_to_daemon.sh 的示例片段（用户手工合入） |

## 5. 接口契约

### 5.1 Unix socket：hook → daemon

**socket path**：`$HOME/.cardputer-daemon/control.sock`
**协议**：一行 JSON + `\n`，客户端写完即关闭。daemon 不回 ack（hook 类消息）；status 请求会回一行 JSON。

**daemon 启动顺序（防 race + 安全）**：

1. `mkdir -p ~/.cardputer-daemon/`（mode 0700，限制 owner-only）
2. open `daemon.lock` + `fcntl.flock(LOCK_EX | LOCK_NB)`，失败 → log + exit 1
3. 探测 `control.sock` 是否可 connect（200ms timeout）；可连接 = 另一实例还在 → 异常状态 → exit 1（理论上步骤 2 已拦但双保险）
4. unlink stale socket 文件（仅当步骤 3 不可连接）
5. bind + chmod 0600 + listen

**错误处理**：
- JSON 解析失败：daemon 丢弃，WARN 日志（不退出）。
- 未识别 `hook_event_name`：丢弃 + WARN。
- 未知 `type` 字段（既不是 hook 也不是 status）：丢弃 + WARN。
- 单个 connection 异常：日志 + 关连接，不影响其他连接。

### 5.2 BLE：daemon → 设备

完全遵循设备端 `buddy_protocol.py` 反推的心跳 schema：

```json
{"msg":"✦ done in foo","total":2,"running":1,"waiting":1,"tokens":17,"tokens_today":17,"entries":3}
```

每帧 `\n` 终止，UTF-8 编码，写到 NUS RX 特征 `6e400002-...`。

**msg 字段编码规则**：单行 ASCII + 少量常用 unicode 符号（✦ 🤖 🪶）。**v0.1 先发，实测看 buddy_ui_cp.py 字体能不能渲染**；乱码就回退纯 ASCII（编码方式记入 SUMMARY.md 实测结果）。

### 5.3 Session 状态机（幂等 upsert）

```python
class Session:
    state: Literal["idle", "running"]
    cwd: str
    started_at: datetime
    last_seen: datetime

def apply_event(event: HookEvent) -> None:
    sid = event["session_id"]
    now = utcnow()
    # 跨日重置（在 upsert 前）
    if now.date() > today_date:
        tokens_today = 0
        entries_today = 0
        today_date = now.date()

    # 幂等 upsert
    if sid not in sessions:
        sessions[sid] = Session(
            state="idle",
            cwd=event.get("cwd", "?"),
            started_at=now,
            last_seen=now,
        )
    else:
        sessions[sid].last_seen = now

    name = event["hook_event_name"]
    if name == "SessionStart":
        # 已 upsert，无额外动作
        latest_event_msg = "🚀 start " + basename(sessions[sid].cwd)
    elif name == "UserPromptSubmit":
        sessions[sid].state = "running"
        entries_today += 1
        latest_event_msg = "🤖 working in " + basename(sessions[sid].cwd)
    elif name == "Stop":
        sessions[sid].state = "idle"
        latest_event_msg = "✦ done in " + basename(sessions[sid].cwd)
    elif name == "SubagentStop":
        # state 保持不变
        latest_event_msg = "🪶 subagent done"
    elif name == "SessionEnd":
        del sessions[sid]
        latest_event_msg = "👋 end " + basename(event.get("cwd", "?"))
    else:
        return  # 未识别事件已在 socket 层拦下

    tokens_today += 1  # 任何被识别的事件都计数

def prune_inactive() -> None:
    """由 event_consumer 在收到 {"type":"prune_tick"} 时调用（不是独立 task 直接改 sessions）。"""
    now = utcnow()
    expired = [sid for sid, s in sessions.items()
               if (now - s.last_seen) > timedelta(minutes=30)]
    for sid in expired:
        del sessions[sid]

# event_consumer 主循环
async def event_consumer(queue):
    while True:
        event = await queue.get()
        etype = event.get("type")
        if etype == "hook":
            apply_event(event)
            hb = compute_heartbeat()
            await ble_client.send_line(hb)
        elif etype == "prune_tick":
            prune_inactive()
            # prune 改变 total/running/waiting，重发一次 heartbeat
            hb = compute_heartbeat()
            await ble_client.send_line(hb)
        elif etype == "status":
            fut = event["future"]
            snapshot = build_status_snapshot(sessions, last_heartbeat, ble_state, ...)
            if not fut.done():
                fut.set_result(snapshot)
```

**ttl_ticker 实现**（独立 task，只投递事件）：

```python
async def ttl_ticker(queue):
    while True:
        await asyncio.sleep(60)
        await queue.put({"type": "prune_tick"})
```

### 5.4 静音逻辑

`os.path.exists(os.path.expanduser("~/.cardputer-mute"))` 返回 True → daemon 不调用 ble_client.send_line（即跳过 BLE 写），但 apply_event 照跑（保持内部状态一致）。

### 5.5 Status 请求（统一走 event_queue + Future）

为保证"单一 event_consumer 串行所有 session_store 访问"不变式成立，status 请求**也通过 event_queue 处理**：

1. socket_server accept → 读到 `{"type":"status"}`
2. 构造 `asyncio.Future()`，投递 `{"type":"status", "future": <fut>}` 到 event_queue
3. event_consumer 收到 status 事件 → 生成快照 dict → `fut.set_result(snapshot)`
4. socket_server `await fut`（带 200ms timeout 兜底死锁）→ 拿到 snapshot → 序列化写回 client socket

快照内容（一行 JSON）：

```json
{"type":"status_reply","schema_version":1,"version":"v0.1","uptime_s":3600,"ble_state":"connected","ble_last_send_error":null,"sessions":{"abc123":{"state":"running","cwd":"/Users/xiaoyangyu/projects/foo","started_at":"2026-05-12T13:00:00Z","last_seen":"2026-05-12T13:30:00Z"}},"tokens_today":17,"entries_today":3,"last_heartbeat":{"msg":"✦ done in foo","total":1,"running":0,"waiting":1,"tokens":17,"tokens_today":17,"entries":3}}
```

`ble_state` ∈ {scanning, connecting, connected, disconnected, backoff}。

## 6. 实施切片

按可独立 commit 单元拆，每片 1-3 文件级别：

### 切片 0：SessionEnd 触发实测（前置任务，遵循 Config 安全规则）

**输出**：双向 diff + 结论写入 SUMMARY.md 附录 "上游 hook 行为验证"。

切片 0 操作 ~/.claude/settings.json（高影响文件），按项目 CLAUDE.md Config 变更安全规则严格执行**先读 → 先 diff → 再改 → 后验**：

1. **先读**：`jq '.hooks // {}' ~/.claude/settings.json > /tmp/hooks-before.json`，保存原 hooks 段。
2. **生成 patch**：用 `jq` 在内存里加临时 SessionEnd hook（command = `bash -c 'echo "$(date) SessionEnd $(jq -r .source) fired" >> /tmp/cc-sessionend-test.log'`），输出到 `/tmp/settings-with-test-hook.json`。
3. **diff 给用户确认**：`diff <(jq -S . ~/.claude/settings.json) <(jq -S . /tmp/settings-with-test-hook.json)`，把 diff 输出给用户拍板。
4. **apply**：用户确认后，`cp /tmp/settings-with-test-hook.json ~/.claude/settings.json`。
5. **后验**：`jq . ~/.claude/settings.json > /dev/null && echo OK || echo SYNTAX_ERROR`。
6. **重启 CC**：/exit 然后重新启动 CC，提示用户做。
7. **实测**：启动 CC、停 CC、再启 CC、清 CC（`/clear`）、resume CC（`/resume`）—— 各场景看 /tmp/cc-sessionend-test.log 有没新行 + source 字段值。
8. **拆 hook（同样的 4 步流程）**：
   - 生成回原状的 patch（`/tmp/settings-restore.json`）
   - diff 给用户确认
   - apply
   - jq . 验证
   - /exit 重启 CC
9. **结论写 SUMMARY.md**：是否触发 / 何场景触发 / source 字段值；双向 diff 内容；TTL 兜底是否仍然必要（答案：是，参见决策 B）。

### 切片 1：session_store + 单元测试

- 文件：`session_store.py`、`tests/test_session_store.py`
- 内容：
  - Session dataclass + apply_event（幂等 upsert）+ compute_heartbeat + prune_inactive + 跨日重置
  - 不依赖：BLE / socket（纯函数）
- 测试覆盖：
  - 5 个 hook 事件按顺序 → 计数 / state 正确
  - **乱序到达**：先 Stop 再 SessionStart（unknown session 兜底 upsert）
  - **daemon 重启场景**：先 UserPromptSubmit 一个 unknown sid → state=running，total=1
  - **TTL prune**：last_seen 31 分钟前 → prune_inactive 删掉
  - **跨日重置**：模拟 mock now 跨日 → tokens_today / entries_today 清零

### 切片 2：socket_server + 单元测试

- 文件：`socket_server.py`、`tests/test_socket_server.py`
- 内容：
  - asyncio unix socket server，accept + 读一行 + 解析 JSON
  - hook 消息投递到 asyncio.Queue（由 daemon 主体注入）
  - status 消息投递 `{"type":"status","future":<fut>}` 到同一 queue，await fut.result（200ms timeout）后写回 client socket。**不走 callback**，统一架构。
  - 启动严格按决策 F 的 5 步顺序
  - 错误隔离：单连接异常不能挂 server
- 测试：起临时 socket，模拟 5 种正常事件 + 1 个 malformed JSON + 1 个 status 请求

### 切片 3：ble_client + offline 单元测试 + 端到端实测

- 文件：`ble_client.py`、`tests/test_ble_client_offline.py`
- 内容：
  - bleak 持续连接 + 指数 backoff（2,4,8,16,32,60 cap）
  - `send_line(payload: dict)`：连接中 → write_gatt_char + 清 dirty；断开 → 只更新 last_heartbeat + 标 dirty
  - reconnect callback → 若 dirty 立即 write last_heartbeat
  - 状态回调（"connected" / "disconnected" / "search_failed"）
  - 单设备硬编码 prefix `Claude_`，保留 env override `CARDPUTER_BLE_NAME`
- 测试（mock bleak）：
  - backoff 序列正确（不能成 0 重试或无限大）
  - send_line 在 disconnected 时只更新 last_heartbeat 不调 write
  - 模拟 disconnect → 收 3 个 send_line → reconnect → 验证只调 1 次 write（最新帧）
- **端到端实测**（设备开机，bridge.py 不在跑）：daemon 跑起来，手动写 socket 触发心跳，肉眼看屏幕 connected 状态 + msg 行刷新。

### 切片 4：daemon 装配 + hook_to_daemon.sh + 静音 + 日志 + flock + 信号 + TTL

- 文件：`daemon.py`、`hook_to_daemon.sh`
- 内容：
  - 三组件装配 + 单一 event_consumer task（决策 D / §4）
  - 单实例 flock（决策 F）
  - RotatingFileHandler 日志
  - 静音逻辑（决策 I）
  - 信号处理（SIGTERM 优雅关 BLE + 删 socket）
  - TTL ticker 独立 task（每分钟投递 prune_tick 到 event_queue，**不直接改 sessions**）
  - event_consumer 派发 hook / prune_tick / status 三类事件
  - hook_to_daemon.sh fallback log 写前 5MB rename rotation
  - status 请求处理（决策 K）
  - hook_to_daemon.sh：50 行内 bash，stdin 读 JSON → 加 `"type":"hook"` → 200ms timeout 写 socket → 失败 append fallback log → exit 0
- 测试：daemon + hook wrapper 联合 dry-run（模拟 5 种 hook 输入喂给 wrapper，wrapper 写 socket，daemon 转发到设备）

### 切片 5：LaunchAgent + 安装/卸载/状态脚本 + 文档

- 文件：`cn.joulian.cardputer-daemon.plist.template`、`scripts/install_daemon.sh`、`scripts/uninstall_daemon.sh`、`scripts/cardputer-daemon-status.sh`、`README-daemon.md`
- install_daemon.sh：
  1. mkdir -p ~/.cardputer-daemon/ 0700
  2. /opt/homebrew/bin/python3 -m venv ~/.cardputer-daemon/venv
  3. ~/.cardputer-daemon/venv/bin/pip install "bleak==<pinned>"
  4. ~/.cardputer-daemon/venv/bin/python -c "import bleak; print(bleak.__version__)"（验证 import）
  5. 替换 plist 模板占位符 → 写到 ~/Library/LaunchAgents/
  6. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`
  7. `launchctl print gui/$(id -u)/cn.joulian.cardputer-daemon | head -20` 显示状态供用户检查
- uninstall_daemon.sh：`launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist` + 删 plist（保留 ~/.cardputer-daemon/ 用户自己手动清）
- cardputer-daemon-status.sh：`(echo '{"type":"status"}'; sleep 0.1) | nc -U ~/.cardputer-daemon/control.sock | jq .`
- README-daemon.md：架构图、装/卸/调试步骤、settings.json hooks 配置示例片段（用户手工合入）、故障排查

### 切片 6：settings.json hooks 配置说明（文档）

- 在 README-daemon.md 里附 settings.json hooks 段示例 + 提示用户拷贝并 **/exit 重启 CC**（hooks 缓存进 session 启动状态，不热重载——见 memory cardputer-adv.md）。
- **不自动改 ~/.claude/settings.json**。

## 7. 测试策略

### 单元测试（自动 + 必跑）

- `tests/test_session_store.py`：覆盖 5 个 hook 事件、乱序、unknown session upsert、TTL prune、跨日重置
- `tests/test_socket_server.py`：5 种正常事件 + malformed + status 请求
- `tests/test_ble_client_offline.py`：mock bleak，backoff 序列、send_line dispatch、reconnect 补发

跑：`cd ~/"Claude Code/cardputer" && ~/.cardputer-daemon/venv/bin/python -m pytest tests/ -v`（用 venv 的 python）

### 集成 smoke（半自动）

`scripts/integration_smoke.sh`：
1. 前台起 daemon（venv python + CARDPUTER_DAEMON_DEBUG=1）
2. wait 5s
3. `nc -U ~/.cardputer-daemon/control.sock` 写 5 种事件 + status 请求
4. grep daemon.log 确认收到 + apply + send_line
5. 优雅终止：`launchctl kickstart -k gui/$(id -u)/cn.joulian.cardputer-daemon` 或直接发 SIGTERM 给已知 PID（PID 从 launchctl print 拿，**先列出来给用户看再操作**）

可选：BLE 真连接。无设备时 send_line 单元测试覆盖即可（端到端实测在切片 3 走）。

### 端到端实测（手动，必跑）

1. 装 LaunchAgent，跑起来
2. 在另一个 shell 起两个 CC session
3. 每个 session 让 CC 干点活（让 Stop 触发）
4. 肉眼看 Cardputer 屏幕：连接图标变 LINKED、msg 行显示最新事件、计数行变化
5. 关一个 session（exit）：屏幕计数减一
6. touch ~/.cardputer-mute：再发消息，屏幕不变；rm 后恢复
7. 跑 `scripts/cardputer-daemon-status.sh`：验证 status JSON 正确

### 重启测试（不使用 pkill -9，严格遵循 Process Safety）

按以下顺序（永不直接 kill）：

1. **场景 A — 进程崩溃自愈**：用 launchctl kickstart 模拟重启
   ```
   launchctl print gui/$(id -u)/cn.joulian.cardputer-daemon | grep -E 'pid|state'
   launchctl kickstart -k gui/$(id -u)/cn.joulian.cardputer-daemon
   ```
   预期：30s 内 launchd 拉起新 PID，新 PID 与旧 PID 不同，屏幕短暂回 idle 然后 LINKED 重出现
2. **场景 B — 设备开关机**：手动关掉 Cardputer 侧边开关
   预期：daemon.log 报 search_failed，60s 内重试；开机后自动重连，dirty=True 时立即重发 last_heartbeat
3. **场景 C — 必须强制终止时**：先列 PID 给用户，由用户决定。脚本绝不自动 kill。
   ```
   launchctl print gui/$(id -u)/cn.joulian.cardputer-daemon | grep -E 'pid'
   # 然后由用户运行：kill -TERM <PID>（注意不是 -9）
   ```

## 8. 风险 / 失败模式

| 风险 | 后果 | 缓解 |
|------|------|------|
| bleak 在 macOS sleep/wake 后连接句柄失效 | daemon 看 connected 状态但 send 失败 | send 失败计数 > 3 → 主动 disconnect 进 backoff 重连 |
| Cardputer BLE name 变了（设备重烧固件改 MAC） | daemon 永远扫不到 | 配 `CARDPUTER_BLE_NAME` env override；日志写明 |
| 用户 ~/.cardputer-daemon/ 目录被删 | socket 失败、daemon 启动崩 | daemon 启动时 `mkdir -p 0700` 自愈 |
| hook 触发频率突增（CC 全自动 loop 模式） | socket 写堆积 | event_queue + 单一 consumer + asyncio drain 应付得了；hook wrapper 端 200ms timeout 限上限 |
| LaunchAgent 拉起前 .sock 文件残留 | bind 失败 | 启动 5 步顺序：先 flock、再 connect 探测、不可连接才 unlink |
| Python venv 损坏 / bleak import 失败 | daemon 反复崩重启循环 | install_daemon.sh 步骤 4 强制 import 校验；ThrottleInterval 30 防 storm |
| BLE 设备同时被别人连（理论上 UIFlow 2.0 不支持，但万一） | daemon 抢不到 | scan 失败 backoff，等待对方释放 |
| daemon 静默崩溃但 launchd 不重启（plist 设错） | 通知功能失效不可见 | install_daemon.sh 用 `launchctl print` 强制验证 + KeepAlive |
| hook_to_daemon.sh 路径含空格 | bash 解析问题 | 所有路径在 hook wrapper 里加双引号 |
| Stop hook 缓存不热重载，settings.json 改后用户没重启 CC | hook 没生效用户以为 daemon 坏了 | README 明写"改完 settings.json 必须 /exit 重启 CC" |
| 多个 CC session 同时写 socket | unix socket accept 多 task + 单 consumer 串行 | 已在 §4 架构里串行化 |
| 写心跳到设备失败 | 日志一堆 ERROR | 失败累计阈值 → disconnect + backoff，避免日志爆炸 |
| BLE disconnect 期间 hook 来一堆事件 | 累计到 reconnect 才下发会落后 | last_heartbeat + dirty 设计保证 reconnect 后只发最新一帧（不补历史） |
| **SessionEnd 上游不触发** | sessions 永久涨 | 切片 0 实测确认；不论结果都靠 30 分钟 TTL 自动清理（决策 B） |
| **hook 写 socket 失败（daemon 没起或崩了）** | 这次事件丢 | hook wrapper append fallback log；TTL 让状态最终一致（用户最差感受：屏幕暂时不准，下个 turn 触发 hook 自动恢复） |

不可逆操作（**仅一处**）：写 `~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist` + `launchctl bootstrap`。提供 `scripts/uninstall_daemon.sh` 一键卸载。

## 9. 待澄清 [OPEN]

无。
