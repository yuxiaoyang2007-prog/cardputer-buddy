我先读三份优先文件，对照 v1 blocker、CC 决定和当前 PLAN 的实际文本，最后只输出 YAML。
已经看到 v2 主体和决策文件。还需要读 PLAN 后半段，重点看测试策略、uninstall 删除语义、hook wrapper/fallback log 是否和前文矛盾。
---
schema_version: 1
review_for: PLAN.md
iteration: 2
reviewer: codex
verdict: revise
blocker_count: 1
suggestion_count: 2
nit_count: 0
first_review_blockers:
  - id: PLAN-3.A
    status: fixed
    sections: ["§3 决策 A", "§6 切片 3", "§8"]
    evidence: "last_heartbeat + dirty flag + reconnect 后立即重发；测试覆盖断连期间 3 个 send_line 后 reconnect 只发最新帧。"
  - id: PLAN-3.B
    status: fixed
    sections: ["§3 决策 B", "§5.3", "§6 切片 0", "§8"]
    evidence: "SessionEnd 不触发由 30 分钟 inactivity TTL 兜底；切片 0 作为前置实测，不论结果 TTL 都保留。"
  - id: PLAN-3.C
    status: fixed
    sections: ["§3 决策 C", "§5.3", "§6 切片 1"]
    evidence: "任何带 session_id 的事件都幂等 upsert；unknown Stop/UserPromptSubmit/SubagentStop 自动创建 session；乱序和重启场景有测试。"
  - id: PLAN-3.D
    status: mostly_fixed
    sections: ["§3 决策 D", "§4", "§6 切片 4", "§8"]
    evidence: "hook 端 200ms timeout + fallback log + exit 0 已落地；但 fallback log 明确 no rotation，见新增 suggestion PLAN-3.D-FALLBACK-ROTATE。"
  - id: PLAN-5.1
    status: mostly_fixed
    sections: ["§4", "§6 切片 4", "§8"]
    evidence: "hook event 经唯一 asyncio.Queue 进入单一 event_consumer；但 TTL pruner 作为独立 task 直接删 sessions，见新增 suggestion PLAN-4.TTL-QUEUE。"
  - id: PLAN-7.1
    status: fixed
    sections: ["§7 重启测试"]
    evidence: "删除 pkill -9；重启用 launchctl kickstart -k；必须终止时先 launchctl print 列 PID，由用户决定 kill -TERM。"
  - id: PLAN-SEC.1
    status: rejected_correctly
    sections: ["cc-decisions-1.md"]
    evidence: "本轮 prompt 已缩窄 prompt injection 定义；项目 CLAUDE.md 描述性规则不再被误报。"
testability_assessment:
  status: acceptable_for_plan_stage
  evidence: "session_store、socket_server、ble_client 都有明确单测切片；integration_smoke 和端到端手测覆盖 daemon 装配、LaunchAgent、双 session、mute、status。未写百分比覆盖率门槛，但关键状态机和 IPC/BLE 风险路径均有 case-level 覆盖。"
sessionend_assessment:
  status: closed
  evidence: "切片 0 放在实现前合理；如果实测 SessionEnd 不触发，§3 决策 B、§5.3、§8 仍通过 30 分钟 TTL 闭合，不依赖 SessionEnd。"
judgment_call: true
---
issues:
  - type: blocker
    id: PLAN-6.0-CONFIG-SAFETY
    judgment_call: false
    section: "§6 切片 0"
    finding: "切片 0 要临时修改 ~/.claude/settings.json 来安装 SessionEnd hook，但没有明确遵循项目 Config 安全规则。"
    evidence: "PLAN 写的是“改 ~/.claude/settings.json，/exit + 重启 CC”“完事拆掉临时 hook”；未写先读、先 diff、再改、jq . 后验，也未要求拆除时同样 diff + jq。"
    impact: "settings.json 是 Claude Code hook 配置的高影响文件；前置实测本身就会触碰核心配置。按当前 PLAN 执行会和项目 CLAUDE.md 的 Config 变更安全规则冲突。"
    required_fix: "在切片 0 明确流程：读取当前 settings.json，生成临时 patch/diff 给用户确认，应用后 jq . 验证，/exit 重启；拆 hook 时同样先 diff、再改、jq . 后验，并把结果写入 SUMMARY。"
  - type: suggestion
    id: PLAN-3.D-FALLBACK-ROTATE
    judgment_call: false
    section: "§3 决策 D / §8"
    finding: "hook-fallback.log 仍是无上限 append，且 PLAN 只说 5MB 手工切、v0.1 no rotation。"
    evidence: "§3 决策 D 写明失败 append 到 ~/.cardputer-daemon/hook-fallback.log，并注明“5MB 时手工切，no rotation in v0.1”；§8 的 hook 触发频率突增风险没有覆盖 fallback log 爆量。"
    impact: "daemon 长时间不可达或 CC 自动 loop 时，hook wrapper 会持续写 fallback log。单行虽小，但 24/7 场景下不应依赖手工切日志。"
    recommended_fix: "让 hook_to_daemon.sh 写 fallback log 前做简单 size cap：超过 5MB rename 为 .1 或 truncate 到最近 N 行；或统一改成 Python wrapper 使用 RotatingFileHandler。"
  - type: suggestion
    id: PLAN-4.TTL-QUEUE
    judgment_call: true
    section: "§4 / §5.3 / §6 切片 4"
    finding: "PLAN 声称 session_store 修改都在单一 event_consumer 内串行，但 TTL pruner 被设计成独立 task 并直接 prune sessions。"
    evidence: "§4 图中有 ttl_pruner 每分钟扫 sessions 删过期；§6 切片 4 写 TTL prune 定时任务；同时 §4 又说 session_store 修改、heartbeat 计算、BLE send 都在单一 task 内串行。"
    impact: "asyncio 单线程下这通常不会造成内存级 data race，但架构不一致，会削弱“单 consumer 解决并发”的可证明性，也让测试边界变模糊。"
    recommended_fix: "把 TTL prune 也建模为 event_queue 的内部事件，例如 {type:'prune_inactive'}，由 event_consumer 处理；或明确 prune_inactive 是无 await 的同步临界段，并补一个 hook 事件与 prune 同时到达的测试。"
