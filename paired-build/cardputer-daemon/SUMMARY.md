# cardputer-daemon v0.1 交付总结

任务：为 M5 Cardputer Adv 写常驻 macOS daemon，维持 24/7 BLE 连接，聚合多 Claude Code session 状态推到设备屏幕。替代之前 Stop hook 直连 BLE "一闪就没" 的临时实现，并修复并发 session 抢 BLE 的问题。

完成时间：2026-05-12
最终方案：PLAN.md（v3，3 轮 review 收敛）
主分支：`main`
最后 commit：`f08cc7a v0.1 polish: README hook path quoting + install plist diff-first + socket WARN + ble disconnect dedup + hook wrapper 单 python`

## 迭代统计

- **方案 review**：3 轮 codex review 收敛（review-plan-1 → review-plan-3）。iteration-1 有 7 blocker + 4 suggestion + 2 nit；iteration-2 全 fixed + 1 新 blocker + 2 新 suggestion；iteration-3 收敛 blocker=0 + 2 fixed suggestion。
- **代码 review**：1 轮 CC review（review-code-1.md）+ 2 轮 codex final-diff 复核（review-final-precommit + review-final-precommit-2）。CC review 0 blocker；codex final 1 抓出 README hook path 空格的 blocker（CC 漏看），codex final 2 验证 polish 充分。
- **升级到用户**：0 次（无卡死信号）

## 改动列表

### 新建文件（cardputer/ 下）

```
daemon.py                                   # asyncio entry + flock + signal + event_consumer + ttl_ticker
session_store.py                            # 幂等 upsert + 跨日重置 + TTL prune + compute_heartbeat
socket_server.py                            # unix socket asyncio + JSON line + status Future
ble_client.py                               # bleak + 持续连接 + backoff + dirty/reconnect 补发
hook_to_daemon.sh                           # CC hook wrapper（单 python 调用 + 5MB log rotation）
cn.joulian.cardputer-daemon.plist.template  # LaunchAgent plist 模板
requirements.txt                            # bleak pinned
scripts/install_daemon.sh                   # venv + diff-first plist + 用户确认 bootstrap
scripts/uninstall_daemon.sh                 # 用户确认 bootout
scripts/cardputer-daemon-status.sh          # status JSON 查询
scripts/integration_smoke.sh                # 端到端 smoke 测试
tests/__init__.py
tests/test_session_store.py                 # 5 tests
tests/test_socket_server.py                 # 4 tests
tests/test_ble_client_offline.py            # 3 tests
README-daemon.md                            # 架构 + 安装 + hooks 配置 + 切片 0 流程 + 故障排查
```

### Commit 列表

```
c85a3c4 Initial commit: cardputer A/B phase artifacts + daemon PLAN
250f87f 切片 1: session_store 幂等 upsert + 单元测试
764b2b2 切片 2: socket_server asyncio unix socket
e0c0b20 切片 3: ble_client 持续连接 + reconnect 补发
521b2c2 切片 4: daemon 装配 + hook wrapper + 静音 + flock
166660d 切片 5: LaunchAgent + 安装/卸载/状态脚本 + 文档
f08cc7a v0.1 polish: README hook path quoting + install plist diff-first + socket WARN + ble disconnect dedup + hook wrapper 单 python
```

合计 16 个新建文件 + 1331 行新增代码。bridge.py / notify_stop.sh / test_long.py / build-with-claude/ 不动。

## 测试覆盖

**单元测试**：

```
.venv/bin/python -m pytest tests/ -v
```

12 passed in 0.01s。覆盖：
- session_store 5 事件状态机 / 乱序 / unknown session upsert / TTL prune / 跨日重置
- socket_server 5 valid hook / malformed JSON / status round-trip / socket 启动顺序+权限
- ble_client backoff 序列 / disconnect 只 buffer 不丢 / reconnect 只发最新一帧

**端到端实测**：

```
scripts/integration_smoke.sh
```

通过。Daemon 启动 → 5 hook 经 wrapper 写 socket → daemon apply event + send heartbeat → status_reply 返回 `tokens_today=5, entries_today=1, sessions={}`（SessionEnd 已删）→ 优雅关停。

**没跑的实测**：
- **真设备 BLE 端到端**：需要 Cardputer 开机 + daemon 装上 + 看屏幕。这是用户接管的"端到端验收"环节（见下方"用户接下来要做的"）。
- **切片 0：SessionEnd 触发实测**：需要改 ~/.claude/settings.json + /exit 重启 CC，涉及用户的 CC session。流程已在 README-daemon.md "Slice 0 SessionEnd Check" 节写清，由用户带 CC 走一遍。

## 已知未覆盖 / Follow-up

| ID | 描述 | 处理 |
|----|------|------|
| FINAL-SMOKE-PRODUCTION-SOCKET | integration_smoke.sh 用生产 socket 路径，daemon 已运行时会被单实例锁拦住但 daemon socket 仍可能被试连 | v0.1 接受。daemon.lock flock 拦住第二实例，不会有真冲突。未来可加 isolated socket env |
| 真实 token 计数 | tokens_today 当前 = hook 事件累计数（活动量指标），不是真实 token | v0.1 设计如此。需要解析 transcript_path 反推 token，列为 follow-up |
| Multi-session sprite 并排显示 | 屏幕 240×135 太小，clawd-tank 的 4-sprite 并排不可行；当前是聚合显示（msg + 计数）| 不计划改 |
| State 持久化 | daemon 重启后 tokens_today / entries_today 归零 | v0.1 接受（玩具用途）；持久化未来再说 |

## 关键决策记录（供后人查）

11 个决策（A-K）写在 PLAN.md §3 全文；3 个 cc-decisions-N.md 记录每轮 review 处理。摘要：

- **A** BLE 24/7 持续连接 + 指数 backoff（2-60s cap）+ last_heartbeat dirty/reconnect 立即补发
- **B** 接 5 hook 事件（SessionStart/SessionEnd/UserPromptSubmit/Stop/SubagentStop）+ 30 分钟 inactivity TTL 兜底（SessionEnd 上游不触发时）
- **C** apply_event 幂等 upsert，未知 session_id 也接（解决 daemon 重启 / SessionStart 丢失）
- **D** Unix socket + JSON line + hook 端 200ms timeout + fallback log 5MB rotation
- **E** Python venv 在 ~/.cardputer-daemon/venv/ 隔离 bleak（不依赖 user-site）
- **F+5.5** asyncio.Queue + 单一 event_consumer 串行（hook / prune_tick / status 全走 queue）+ Status 走 Future
- **G** BLE 单 host 独占设备（daemon 跑着时 bridge.py 不能用）
- **H** daemon 内态不持久化（v0.1 接受重启清零）
- **I** 静音逻辑放 daemon 端（~/.cardputer-mute 存在 → 不发 BLE 但内部状态正常）
- **J** 保留 notify_stop.sh / 新增 hook_to_daemon.sh / settings.json 由用户手工 diff 后改
- **K** Status 命令查询 BLE state / sessions / last_heartbeat（scripts/cardputer-daemon-status.sh）

## 用户接下来要做的（真设备投产）

按以下顺序，每步可单独中止：

### 1. 安装 daemon

```bash
cd ~/"Claude Code/cardputer"
scripts/install_daemon.sh
```

会创建 ~/.cardputer-daemon/venv，pip install bleak，渲染 plist 模板。**两个 read -p 确认步骤**：
- 是否写 `~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`（先 diff 给你看）
- 是否跑 `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/cn.joulian.cardputer-daemon.plist`

回 `n` 任一步骤即可中止，已生成文件不动。

### 2. 装好后看状态

```bash
scripts/cardputer-daemon-status.sh
```

预期：`"ble_state": "scanning"` 或 `"connected"`（如果 Cardputer 在 Buddy app 且 BLE 广播中）。

### 3. 改 settings.json hooks（手工）

按 README-daemon.md 示例（5 个 hook，每个 command 用 `bash '...'` 包路径），先 diff，再改，jq . 验证，**/exit 重启 CC**。

### 4. 切片 0：SessionEnd 触发实测

按 README-daemon.md "Slice 0 SessionEnd Check" 流程做，结果记录到这份 SUMMARY 的末尾（手工 append）。

### 5. 真设备端到端验收

1. Cardputer 切到 Buddy app
2. 起两个 CC session
3. 在每个 session 让 CC 干点活
4. 看 Cardputer 屏幕：LINKED 图标 + msg 行刷新 + 计数变化

### 卸载

```bash
scripts/uninstall_daemon.sh
```

回 `y` 确认 bootout 卸载 LaunchAgent + 删 plist。保留 ~/.cardputer-daemon/（log + venv）方便后续检查。

### 回滚路径

把 ~/.claude/settings.json 的 5 个 hook command 改回 notify_stop.sh + /exit 重启 CC，恢复 A 阶段的 fire-and-forget 行为。
